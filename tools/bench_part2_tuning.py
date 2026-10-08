"""Serial local dual-GPU tuning; retain responses and validate before adopting settings."""
import argparse
import ast
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys
import threading
import time
import urllib.request
import _thread

ROOT = Path(__file__).resolve().parents[1]
OUT = None
BASE = None
PORT = 18997


def corpus(training=False, extended=False, medium=False):
    if training:
        return [('train_qa', 'Explain in about 200 words how virtual memory, page faults, RAM and SSD storage interact.', 320),
                ('train_code', 'Write a Python function that merges two sorted lists. Explain its time complexity and provide three examples.', 380),
                ('train_text', '用中文解释 GPU 显存、CPU 内存和 PCIe 带宽如何影响大语言模型推理，约300字。', 450)]
    rows = '\n'.join(f'Record {i}: code=K{i:04d}; stock={(i*17+3)%97}.' for i in range(100))
    cases = [('qa', 'Return only a JSON object with keys planet, product, sorted. Set planet to the largest planet in the solar system in English, product to 17 times 23, sorted to the numbers 9, -2, 5, 0 in ascending order.', 100),
            ('code', 'Write only Python code, no explanation. Define stable_unique(items) that removes duplicates from a list of hashable values while preserving first occurrence order. Do not import anything. Use a set to achieve average O(n) time.', 220),
            ('long', rows + '\nReturn only a JSON array of stock values for records 7, 23, 51, 88 and 99, in that order.', 100),
            ('decode', 'Return only a JSON array containing the squares of all integers from 1 through 60 inclusive, in ascending order. Do not omit any number.', 500)]
    if extended:
        cases += [('prose', 'Explain how a browser resolves a domain name using DNS, including recursive resolvers, caching, TTL expiration, and the difference between authoritative and recursive servers. Use about 220 English words.', 420),
                  ('long5k', '\n'.join(f'Record {i}: code=K{i:04d}; stock={(i*17+3)%97}.' for i in range(260)) + '\nReturn only a JSON array of stock values for records 7, 23, 51, 88 and 99, in that order.', 100),
                  ('cache_first', 'Answer with the number only: what is 2 plus 2?', 16),
                  ('cache_repeat', 'Answer with the number only: what is 2 plus 2?', 16)]
    if medium:
        cases.insert(2, ('medium', '\n'.join(f'Item {i}: id=R{i:04d}; available={(i*13+5)%89}.' for i in range(50)) + '\nReturn only a JSON array of available values for items 7, 23, 31, 38 and 49, in that order.', 100))
    return cases


def validate(key, answer):
    answer = re.sub(r'^```(?:python|json)?\s*|\s*```$', '', answer.strip())
    if key == 'qa':
        assert json.loads(answer) == dict(planet='Jupiter', product=391, sorted=[-2, 0, 5, 9]), answer
    elif key in ('long', 'long5k'):
        assert json.loads(answer) == [(i*17+3)%97 for i in (7, 23, 51, 88, 99)], answer
    elif key == 'medium':
        assert json.loads(answer) == [(i*13+5)%89 for i in (7, 23, 31, 38, 49)], answer
    elif key == 'decode':
        assert json.loads(answer) == [i*i for i in range(1, 61)], answer
    elif key.startswith('cache_'):
        assert answer.strip() == '4', answer
    elif key == 'prose':
        assert len(answer.split()) >= 130
        assert all(word in answer.lower() for word in ('recursive', 'authoritative', 'ttl'))
    elif key == 'code':
        tree = ast.parse(answer)
        assert len(tree.body) == 1 and isinstance(tree.body[0], ast.FunctionDef)
        assert tree.body[0].name == 'stable_unique' and not tree.body[0].decorator_list
        allowed = {'set', 'list', 'len', 'range', 'enumerate'}
        for node in ast.walk(tree):
            assert not isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.While))
            if isinstance(node, ast.Name):
                assert not node.id.startswith('__')
            if isinstance(node, ast.Attribute):
                assert node.attr in ('add', 'append')
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id in allowed
        ns = {'__builtins__': {n: getattr(__import__('builtins'), n) for n in allowed}}
        exec(compile(tree, '<candidate>', 'exec'), ns)
        for values, expected in [([], []), ([3, 1, 3, 2, 1], [3, 1, 2]), (['b', 'a', 'b'], ['b', 'a']), ([None, 0, None, 0], [None, 0])]:
            assert ns['stable_unique'](values) == expected


def worker(label, overrides, training, extended, thresholds, rounds, medium, suite=None, coding_thresholds=()):
    cases_for, check_response = suite or (corpus, validate)
    OUT.mkdir(parents=True, exist_ok=True)
    config = json.loads(BASE.read_text(encoding='utf-8'))
    args = config['args']
    for name, value in overrides.items():
        if name == 'env':
            config['env'] = {**config.get('env', {}), **value}
            continue
        if name == 'exe':
            config['exe'] = value
            continue
        flag = '--' + name.replace('_', '-')
        if flag in args:
            args[args.index(flag)+1] = str(value)
        else:
            args.extend([flag, str(value)])
    if training:
        args.extend(['--dump-routing', str(OUT / (label + '.routing'))])
    config['log'] = str(OUT / (label + '-engine.log'))
    path = OUT / (label + '-config.json')
    path.write_text(json.dumps(config, indent=2), encoding='utf-8')

    def request(endpoint, data=None):
        req = urllib.request.Request(f'http://127.0.0.1:{PORT}' + endpoint,
                                     data=None if data is None else json.dumps(data).encode(),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=300) as response:
            return json.load(response)

    def test():
        result = dict(label=label, overrides=overrides, requests=[], ok=False)
        target = OUT / (label + '-result.json')
        try:
            deadline = time.monotonic() + 360
            while True:
                try:
                    result['health'] = request('/health')
                    break
                except Exception:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(1)
            cases = cases_for(training, extended, medium)
            cases += [(f'{key}@{round_number}', prompt, limit) for round_number in range(2, rounds+1)
                      for key, prompt, limit in cases_for(training, extended, medium)]
            if thresholds:
                cases += [(f'{key}:p{percent}', prompt, limit) for percent in (90, 95)
                          for key, prompt, limit in corpus(False, True) if key in ('code', 'decode', 'prose')]
            if coding_thresholds:
                cases += [(f'{key}:p{percent}', prompt, limit) for percent in coding_thresholds
                          for key, prompt, limit in cases_for() if key != 'probe']
            result['expected_requests'] = len(cases)
            result['cases'] = [dict(key=key, prompt=prompt, max_tokens=limit) for key, prompt, limit in cases]
            for key, prompt, limit in cases:
                start = time.monotonic()
                base_key = key.split('@')[0].split(':')[0]
                tuning = {} if ':' not in key else {'spec_min_p': int(key.split(':p')[1])/100}
                response = request('/v1/chat/completions', dict(model='qwen3.8-flash-next',
                    messages=[dict(role='user', content=prompt)], max_tokens=limit, temperature=0,
                    chat_template_kwargs={'enable_thinking': False}, strata_tune=tuning, stream=False))
                entry = dict(key=key, seconds=time.monotonic()-start, response=response)
                result['requests'].append(entry)
                try:
                    if not training:
                        check_response(base_key, response['choices'][0]['message']['content'])
                        if suite is not None:
                            assert response['choices'][0]['finish_reason'] == 'stop', 'code output was truncated'
                        if base_key == 'cache_repeat':
                            assert response['timings']['cache_n'] > 0, 'repeat did not reuse the prompt cache'
                    entry['valid'] = True
                except Exception as error:
                    entry.update(valid=False, error=repr(error))
                target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            result['status'] = request('/v1/status')
            result['ok'] = all(r['valid'] for r in result['requests'])
        except Exception as error:
            result['error'] = repr(error)
        finally:
            target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            _thread.interrupt_main()

    sys.path[:0] = [str(ROOT/'serve'), str(ROOT/'tools')]
    threading.Thread(target=test, daemon=True).start()
    sys.argv = ['server.py', '--engine', 'strata', '--config', str(path), '--host', '127.0.0.1', '--port', str(PORT)]
    runpy.run_path(str(ROOT/'serve/server.py'), run_name='__main__')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('label')
    parser.add_argument('--config', type=Path, required=True, help='Base Strata server config; never modified')
    parser.add_argument('--out', type=Path, required=True, help='Directory for logs, config copies and responses')
    parser.add_argument('--port', type=int, default=18997, help='Local benchmark port')
    parser.add_argument('--overrides', default='{}')
    parser.add_argument('--training', action='store_true')
    parser.add_argument('--extended', action='store_true')
    parser.add_argument('--thresholds', action='store_true')
    parser.add_argument('--rounds', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--medium', action='store_true')
    parser.add_argument('--coding', action='store_true', help='Long Python code tasks with functional checks')
    parser.add_argument('--coding-long', action='store_true', help='Add a larger matrix module')
    parser.add_argument('--coding-edit', action='store_true', help='Add a complete-module editing task')
    parser.add_argument('--coding-cases', default='', help='Select comma-separated coding case names')
    parser.add_argument('--coding-thresholds', default='', help='Extra coding passes at comma-separated confidence percentages')
    parser.add_argument('--worker', action='store_true')
    opts = parser.parse_args()
    BASE, OUT, PORT = opts.config.resolve(), opts.out.resolve(), opts.port
    suite = None
    coding_thresholds = [int(p) for p in opts.coding_thresholds.split(',') if p]
    if any(p < 0 or p > 100 for p in coding_thresholds):
        parser.error('confidence percentages must be in 0..100')
    if (opts.coding_long or opts.coding_edit or opts.coding_cases or coding_thresholds) and not opts.coding:
        parser.error('coding options require --coding')
    if opts.coding:
        if opts.training or opts.extended or opts.medium or opts.thresholds:
            parser.error('--coding is a separate suite; use --rounds and --overrides with it')
        from bench_mtp_coding import corpus as coding_corpus, validate as coding_validate
        coding_cases = coding_corpus(long=opts.coding_long, editing=opts.coding_edit)
        if opts.coding_cases:
            selected = set(opts.coding_cases.split(','))
            unknown = selected - {key for key, _, _ in coding_cases}
            if unknown:
                parser.error('unknown coding cases: ' + ', '.join(sorted(unknown)))
            coding_cases = [case for case in coding_cases if case[0] in selected]
        suite = (lambda *_: list(coding_cases), coding_validate)
    if not opts.worker and (OUT/(opts.label+'-result.json')).exists():
        parser.error('this label already has a result; choose a new label to preserve it')
    if opts.worker:
        worker(opts.label, json.loads(opts.overrides), opts.training, opts.extended, opts.thresholds, opts.rounds, opts.medium, suite, coding_thresholds)
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        with (OUT/(opts.label+'-server.log')).open('w', encoding='utf-8') as log:
            child = subprocess.Popen([sys.executable, '-X', 'utf8', __file__, *sys.argv[1:], '--worker'], stdout=log, stderr=subprocess.STDOUT)
            try:
                child.wait(timeout=900)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True)
                raise
        result = json.loads((OUT/(opts.label+'-result.json')).read_text(encoding='utf-8'))
        print(json.dumps(dict(label=opts.label, ok=result['ok'], measurements=[dict(key=r['key'], valid=r['valid'], seconds=r['seconds'], timings=r['response'].get('timings')) for r in result['requests']]), ensure_ascii=False), flush=True)
        sys.exit(0 if result['ok'] else 1)
