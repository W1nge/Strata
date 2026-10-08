"""Serial, bounded HTTP regression with complete responses and Windows memory/disk counters.

Cold cases require cache_n == 0. Use the frozen sessions fixture and --prefix for cache regression.
All outputs use a fresh label. The server binds only loopback and owns its engine process.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import threading
import time
import urllib.request

import psutil

OUT = Path(__file__).resolve().parent
ROOT = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr')
URL = 'http://127.0.0.1:18997'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def request(endpoint, body=None, timeout=5):
    req = urllib.request.Request(URL+endpoint, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def stream_request(body):
    started = time.perf_counter()
    req = urllib.request.Request(URL+'/v1/chat/completions', data=json.dumps(body).encode(),
                                 headers={'Content-Type':'application/json'})
    chunks, answer, first, finish, usage, timings = [], [], None, None, None, None
    with urllib.request.urlopen(req, timeout=240) as response:
        for raw in response:
            line = raw.decode('utf-8').strip()
            if not line.startswith('data:') or line.endswith('[DONE]'):
                continue
            event = json.loads(line[5:])
            chunks.append(event)
            if event.get('error'):
                raise RuntimeError(event['error'])
            for choice in event.get('choices', []):
                delta = choice.get('delta', {})
                if delta.get('reasoning_content'):
                    raise AssertionError('Unexpected reasoning output')
                piece = delta.get('content') or ''
                if piece:
                    if first is None:
                        first = time.perf_counter()-started
                    answer.append(piece)
                if choice.get('finish_reason'):
                    finish = choice['finish_reason']
            usage = event.get('usage', usage)
            timings = event.get('timings', timings)
    return dict(text=''.join(answer), ttft_s=first, wall_s=time.perf_counter()-started,
                finish=finish, usage=usage, timings=timings, chunks=chunks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label')
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--server-root', type=Path, default=ROOT)
    parser.add_argument('--fixture', type=Path, default=OUT/'prefill-fixture.json')
    parser.add_argument('--prefix', action='store_true')
    args = parser.parse_args()
    target = OUT/(args.label+'-result.json')
    cfg_path = OUT/(args.label+'-config.json')
    if target.exists() or cfg_path.exists():
        parser.error('Use a new label; earlier evidence is preserved')
    for p in psutil.process_iter(['pid','name']):
        if (p.info['name'] or '').lower() in ('strata.exe','nvcc.exe','cmake.exe'):
            raise RuntimeError(f'Another model or build is running: {p.info}')
    for connection in psutil.net_connections(kind='tcp'):
        if connection.status == psutil.CONN_LISTEN and connection.laddr.port == 18997:
            raise RuntimeError('Benchmark port is already in use')
    cfg = json.loads(args.config.read_text(encoding='utf-8'))
    cfg['log'] = str(OUT/(args.label+'-engine.log'))
    save(cfg_path, cfg)
    fixture = json.loads(args.fixture.read_text(encoding='utf-8'))
    command = [sys.executable,'-X','utf8','-m','serve.server','--engine','strata','--config',str(cfg_path),
               '--host','127.0.0.1','--port','18997']
    result = dict(label=args.label, ok=False, requests=[], started_epoch=time.time(), command=command,
        server_root=str(args.server_root), server_commit=subprocess.check_output(['git','rev-parse','HEAD'],
            cwd=args.server_root, text=True).strip(), config_sha256=sha(cfg_path),
        exe_sha256=sha(Path(cfg['exe'])), fixture_sha256=sha(args.fixture), expected_requests=len(fixture))
    result['gpu_before'] = subprocess.check_output(['nvidia-smi',
        '--query-gpu=index,name,driver_version,power.limit,memory.total','--format=csv,noheader'], text=True).strip()
    if '537.13' not in result['gpu_before'] or '310.00' not in result['gpu_before']:
        raise RuntimeError('Driver/power preflight differs from the agreed baseline')
    env = dict(os.environ)
    for key in list(env):
        if key.startswith('STRATA_'):
            env.pop(key)
    sample = runpy.run_path(str(OUT/'monitor_windows.py'))['sample']
    stop = threading.Event()
    with (OUT/(args.label+'-server.log')).open('x', encoding='utf-8') as log:
        server = subprocess.Popen(command, cwd=args.server_root, env=env, stdout=log,
            stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        result['server_pid'] = server.pid
        owner = psutil.Process(server.pid)

        def cleanup():
            try:
                processes = owner.children(recursive=True)+[owner]
            except psutil.NoSuchProcess:
                return
            for process in processes:
                try:
                    process.terminate()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs(processes, timeout=5)
            for process in alive:
                try:
                    process.kill()
                except psutil.NoSuchProcess:
                    pass

        def monitor():
            with (OUT/(args.label+'-memory.jsonl')).open('x', encoding='utf-8') as f:
                while not stop.is_set():
                    try:
                        item = sample(owner)
                        item.update(completed_requests=len(result['requests']), current_request=result.get('current_request'))
                    except Exception as error:
                        item = dict(epoch_s=time.time(), error=repr(error))
                    f.write(json.dumps(item)+'\n')
                    f.flush()
                    stop.wait(1)

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        watchdog = threading.Timer(900, cleanup)
        watchdog.start()
        try:
            deadline = time.monotonic()+360
            while True:
                if server.poll() is not None:
                    raise RuntimeError('Server exited during startup')
                try:
                    health = request('/health', timeout=2)
                    if health.get('loaded') and health.get('status') == 'ok':
                        result['health'] = health
                        break
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError('Server did not become ready')
                time.sleep(1)
            for case in fixture:
                body = copy.deepcopy(case['request'])
                if args.prefix and case.get('pin'):
                    body['strata_prefix'] = case['pin']
                result['current_request'] = case['key']
                row = dict(key=case['key'], group=case['group'], request=body,
                    expected=case['expected'], started_epoch=time.time())
                save(target, result)
                row.update(stream_request(body))
                answer = re.sub(r'^```(?:json)?\s*|\s*```$', '', row['text'].strip())
                try:
                    row['valid'] = row['finish'] == 'stop' and row['timings'] is not None and json.loads(answer) == case['expected']
                    if case['group'] == 'cold':
                        row['valid'] = row['valid'] and row['timings'].get('cache_n') == 0
                except (ValueError, TypeError) as error:
                    row.update(valid=False, validation_error=repr(error))
                row['metrics'] = request('/metrics')
                result['requests'].append(row)
                save(target, result)
                print(json.dumps({k:row[k] for k in ('key','valid','text','ttft_s','wall_s','timings')}, ensure_ascii=False), flush=True)
                if not row['valid']:
                    raise AssertionError('Invalid response or cache hit: '+case['key'])
            result['status'] = request('/v1/status')
            result['ok'] = len(result['requests']) == len(fixture) and all(r['valid'] for r in result['requests'])
        except Exception as error:
            result['error'] = repr(error)
            raise
        finally:
            result['ended_epoch'] = time.time()
            save(target, result)
            watchdog.cancel()
            stop.set()
            thread.join(timeout=4)
            try:
                result['unload'] = request('/unload', {}, timeout=20)
            except Exception as error:
                result['unload_error'] = repr(error)
            cleanup()
            server.wait(timeout=10)
            result['gpu_after'] = subprocess.run(['nvidia-smi','--query-gpu=index,name,driver_version,power.limit',
                '--format=csv,noheader'], capture_output=True, text=True).stdout.strip()
            save(target, result)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
