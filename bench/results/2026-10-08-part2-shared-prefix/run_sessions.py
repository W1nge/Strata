"""Bounded, serial HTTP comparison of existing prefix pinning and conversation parking.

Run control-a first to freeze actual multi-turn requests, then replay that fixture.
All model requests stay on a private loopback port. No source or driver changes.
"""
from __future__ import annotations

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

ROOT = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr')
OUT = Path(__file__).resolve().parent
LIVE = Path('C:/strata-models/strata-dual-p100-coding.json')
PORT = 18997
URL = f'http://127.0.0.1:{PORT}'
SYSTEM = 'You are a careful code reviewer. Use the supplied source and the latest tool result. Return only the requested JSON, with no markdown or explanation.'
TOOLS = [{'type': 'function', 'function': {'name': 'read_test_report',
          'description': 'Read the latest local test report supplied by the client.',
          'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}}]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def json_request(endpoint, body=None, timeout=5):
    request = urllib.request.Request(URL + endpoint,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def body(messages, *, tools=False, checkpoint=True):
    value = dict(model='qwen3.8-flash-next', messages=messages, temperature=0,
                 max_tokens=96, stream=True, chat_template_kwargs={'enable_thinking': False})
    if tools:
        value['tools'] = copy.deepcopy(TOOLS)
        # Tool results below are fixtures. The model must answer, not request another tool.
        value['tool_choice'] = 'none'
    if not checkpoint:
        value['strata_checkpoint'] = False
    return value


def stream_request(value):
    started = time.perf_counter()
    request = urllib.request.Request(URL + '/v1/chat/completions',
        data=json.dumps(value).encode(), headers={'Content-Type': 'application/json'})
    chunks, answer, first, finish, usage, timings = [], [], None, None, None, None
    with urllib.request.urlopen(request, timeout=240) as response:
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
                        first = time.perf_counter() - started
                    answer.append(piece)
                if choice.get('finish_reason'):
                    finish = choice['finish_reason']
            usage = event.get('usage', usage)
            timings = event.get('timings', timings)
    return dict(text=''.join(answer), ttft_s=first, wall_s=time.perf_counter()-started,
                finish=finish, usage=usage, timings=timings, chunks=chunks)


def build_cases(send):
    send('warm', 'warm', body([{'role': 'user', 'content': 'Return only the JSON number for 2 plus 2.'}], checkpoint=False), 4)
    a = (ROOT/'tools/research_run.py').read_text(encoding='utf-8')
    b = (ROOT/'tools/bench_part2_tuning.py').read_text(encoding='utf-8')
    sources = {'A': a, 'B': b}
    for i, (question, expected) in enumerate([
        ('Return only a JSON array naming the function that builds a request body, then the function that sends one HTTP request.', ['request_body', 'ask']),
        ('Return only a JSON array of the accepted values of --layout, in the order given in the argument parser.', ['split', 'joined']),
        ('Return only a one-element JSON array containing the default for --max-tokens. Format: [number].', [128]),
        ('Return only a JSON array of the accepted values of --prefix, in the order given in the argument parser.', ['on', 'off']),
    ]):
        document = 'Source file: tools/research_run.py\n```python\n' + a + '\n```\n\n'
        request = body([{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': document + question}])
        send(f'prefix-{i}', 'prefix', request, expected, {'message': 1, 'chars': len(document)})
    for name, source, expected in [('changed', a.replace('default=128)', 'default=192)'), 192), ('original', a, 128)]:
        document = 'Source file: tools/research_run.py\n```python\n' + source + '\n```\n\n'
        request = body([{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': document + 'Return only a one-element JSON array containing the default for --max-tokens. Format: [number].'}])
        send('prefix-' + name, 'prefix-edit', request, [expected], {'message': 1, 'chars': len(document)})

    histories = {}
    questions = {'A': ('Return only a JSON array naming the function that builds a request body, then the function that sends one HTTP request.', ['request_body', 'ask']),
                 'B': ('Return only a JSON array naming the function that creates the test corpus, then the function that validates responses.', ['corpus', 'validate'])}
    for project in ('A', 'B'):
        question, expected = questions[project]
        messages = [{'role': 'system', 'content': SYSTEM},
                    {'role': 'user', 'content': f'Project {project}. Review this Python source.\n```python\n{sources[project]}\n```\n\n{question}'}]
        answer = send(project+'0', 'session-initial', body(messages, tools=True), expected)
        histories[project] = messages + [{'role': 'assistant', 'content': answer}]
    for project, question, expected in [('A', 'Return only a one-element JSON array containing the default for --max-tokens. Format: [number].', [128]),
                                        ('B', 'Return only a one-element JSON array containing the value of the module constant PORT. Format: [number].', [18997])]:
        messages = histories[project] + [{'role': 'user', 'content': question}]
        answer = send(project+'1', 'session-return', body(messages, tools=True), expected)
        histories[project] = messages + [{'role': 'assistant', 'content': answer}]
    tool_prefixes = {}
    for project, count in [('A', 3), ('B', 7)]:
        messages = histories[project] + [
            {'role': 'user', 'content': 'Use the test report and return only a one-element JSON array containing its failed_tests value. Format: [number].'},
            {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'report_'+project, 'type': 'function',
                'function': {'name': 'read_test_report', 'arguments': '{}'}}]}]
        tool_prefixes[project] = copy.deepcopy(messages)
        messages += [{'role': 'tool', 'tool_call_id': 'report_'+project,
                      'content': json.dumps({'project': project, 'failed_tests': count, 'passed_tests': 41})}]
        answer = send(project+'2', 'session-tool', body(messages, tools=True), [count])
        histories[project] = messages + [{'role': 'assistant', 'content': answer}]
    for project, count in [('A', 5), ('B', 9)]:
        messages = tool_prefixes[project] + [{'role': 'tool', 'tool_call_id': 'report_'+project,
                    'content': json.dumps({'project': project, 'failed_tests': count, 'passed_tests': 39})}]
        answer = send(project+'3', 'session-rewind', body(messages, tools=True), [count])
        histories[project] = messages + [{'role': 'assistant', 'content': answer}]
    for project, count in [('A', 5), ('B', 9)]:
        messages = histories[project] + [{'role': 'user', 'content': 'Return only a one-element JSON array containing the latest failed_tests value again. Format: [number].'}]
        send(project+'4', 'session-return', body(messages, tools=True), [count])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label')
    parser.add_argument('--candidate', action='store_true')
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--exe', type=Path)
    args = parser.parse_args()
    target = OUT/(args.label+'-result.json')
    if target.exists() or (args.freeze and (OUT/'fixture.json').exists()):
        parser.error('Choose a new label; evidence is never overwritten')
    if args.freeze and args.candidate:
        parser.error('Freeze the baseline responses first')
    baseline = OUT/'baseline-coding-config.json'
    if not baseline.exists():
        baseline.write_bytes(LIVE.read_bytes())
    cfg = json.loads(baseline.read_text(encoding='utf-8'))
    if args.exe:
        cfg['exe'] = str(args.exe.resolve())
    if args.candidate:
        for flag, value in {'--prompt-cache': '3', '--conversation-cache-mib': '1536',
                            '--conversation-cache-slots': '2', '--conversation-cache-min-free-mib': '6144'}.items():
            if flag in cfg['args']:
                cfg['args'][cfg['args'].index(flag)+1] = value
            else:
                cfg['args'] += [flag, value]
    cfg['log'] = str(OUT/(args.label+'-engine.log'))
    config = OUT/(args.label+'-config.json')
    save(config, cfg)
    command = [sys.executable, '-X', 'utf8', '-m', 'serve.server', '--engine', 'strata',
               '--config', str(config), '--host', '127.0.0.1', '--port', str(PORT)]
    result = dict(label=args.label, candidate=args.candidate, ok=False, requests=[],
                  config_sha256=digest(config), exe_sha256=digest(Path(cfg['exe'])), command=command,
                  started_epoch=time.time())
    fixture = []
    stop = threading.Event()
    env = dict(os.environ)
    for key in ('STRATA_TRACE', 'STRATA_PREFILL_TIMING', 'STRATA_STATE_HASH', 'STRATA_SNAPSHOT_VERIFY',
                'STRATA_CPU_PROFILE', 'STRATA_DECODE_TIMING', 'STRATA_LOGPOS', 'STRATA_VERIFY_PROFILE',
                'STRATA_CACHE_MESSAGE_BOUNDARY'):
        env.pop(key, None)
    for connection in psutil.net_connections(kind='tcp'):
        if connection.status == psutil.CONN_LISTEN and connection.laddr.port == PORT:
            raise RuntimeError(f'Test port {PORT} is already in use')
    gpu = subprocess.run(['nvidia-smi', '--query-gpu=index,name,driver_version,power.limit,memory.total',
                          '--format=csv,noheader'], capture_output=True, text=True, check=True)
    result['gpu_before'] = gpu.stdout.strip()
    sample = runpy.run_path(str(ROOT/'bench/results/2026-10-04-windows-mapped-release/monitor_windows.py'))['sample']
    with (OUT/(args.label+'-server.log')).open('x', encoding='utf-8') as log:
        server = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        result['server_pid'] = server.pid
        owner = psutil.Process(server.pid)
        def cleanup():
            try:
                processes = owner.children(recursive=True) + [owner]
            except psutil.NoSuchProcess:
                return
            for process in processes:
                try:
                    process.terminate()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(processes, timeout=8)
        def monitor():
            with (OUT/(args.label+'-memory.jsonl')).open('x', encoding='utf-8') as stream:
                while not stop.is_set():
                    try:
                        item = sample(owner)
                        item.update(completed_requests=len(result['requests']), current_request=result.get('current_request'))
                    except Exception as error:
                        item = {'epoch_s': time.time(), 'error': repr(error)}
                    stream.write(json.dumps(item)+'\n')
                    stream.flush()
                    stop.wait(1)
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        watchdog = threading.Timer(900, cleanup)
        watchdog.start()
        def send(key, group, request, expected, pin=None):
            frozen = dict(key=key, group=group, request=copy.deepcopy(request), expected=expected, pin=pin)
            if args.freeze:
                fixture.append(frozen)
            outgoing = copy.deepcopy(request)
            if args.candidate and pin:
                outgoing['strata_prefix'] = pin
            result['current_request'] = key
            row = dict(key=key, group=group, request=outgoing, expected=expected, started_epoch=time.time())
            save(target, result)
            response = stream_request(outgoing)
            row.update(response)
            stripped = re.sub(r'^```(?:json)?\s*|\s*```$', '', response['text'].strip())
            try:
                row['valid'] = response['finish'] == 'stop' and response['timings'] is not None and json.loads(stripped) == expected
            except (ValueError, TypeError) as error:
                row.update(valid=False, validation_error=repr(error))
            row['metrics'] = json_request('/metrics')
            result['requests'].append(row)
            save(target, result)
            print(json.dumps({k: row[k] for k in ('key', 'valid', 'text', 'ttft_s', 'wall_s', 'timings')}, ensure_ascii=False), flush=True)
            if not row['valid']:
                raise AssertionError('Invalid response: '+key)
            return response['text']
        try:
            deadline = time.monotonic()+360
            while True:
                if server.poll() is not None:
                    raise RuntimeError('Server exited during startup')
                try:
                    health = json_request('/health', timeout=2)
                    if health.get('loaded') and health.get('status') == 'ok':
                        result['health'] = health
                        break
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError('Server did not become ready')
                time.sleep(1)
            if args.freeze:
                build_cases(send)
                save(OUT/'fixture.json', fixture)
            else:
                fixture = json.loads((OUT/'fixture.json').read_text(encoding='utf-8'))
                for case in fixture:
                    send(case['key'], case['group'], case['request'], case['expected'], case['pin'])
            result['status'] = json_request('/v1/status')
            result['expected_requests'] = len(fixture)
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
                result['unload'] = json_request('/unload', {}, timeout=20)
            except Exception as error:
                result['unload_error'] = repr(error)
            cleanup()
            server.wait(timeout=10)
            result['gpu_after'] = subprocess.run(['nvidia-smi', '--query-gpu=index,name,driver_version,power.limit',
                '--format=csv,noheader'], capture_output=True, text=True).stdout.strip()
            save(target, result)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
