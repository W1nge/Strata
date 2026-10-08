"""Freeze current installation and bounded, cache-miss inputs for the 0.1.41 comparison."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr')
DAILY = Path('C:/Users/Winge/.zcode/workspace/default/Strata')
OUT = Path(__file__).resolve().parent
OLD = Path('E:/strata-setup/part2-prefix-20261008')


def save(name, value):
    with (OUT/name).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


base = json.loads((OUT/'baseline-coding-config.json').read_text(encoding='utf-8'))
save('preflight.json', dict(epoch=time.time(), integration_base='07c4d8c65c0dccc169025c3ee79958062d7a04bc',
    upstream='fb58e0dbc8399662c0e47c76578c6e878b14f6cf',
    merged_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    daily_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=DAILY, text=True).strip(),
    baseline_config_sha256=sha(OUT/'baseline-coding-config.json'), baseline_exe_sha256=sha(Path(base['exe'])),
    audit_sha256=sha(DAILY/'docs/performance/UPSTREAM-OPTIMIZATION-AUDIT-2026-10-08.md'),
    inherited_strata_env={k:v for k,v in os.environ.items() if k.startswith('STRATA_')},
    gpu=subprocess.check_output(['nvidia-smi', '--query-gpu=index,name,driver_version,power.limit,memory.total',
                                  '--format=csv,noheader'], text=True).strip()))
for label, env in [('v141-default', {}), ('v141-no-share', {'STRATA_PREFILL_CPU_SHARE':'0'}),
                   ('v141-share3072', {'STRATA_PREFILL_CPU_SHARE':'auto', 'STRATA_PREFILL_CPU_SHARE_MAX':'3072'})]:
    cfg = copy.deepcopy(base)
    cfg['exe'] = str(OUT/'upstream-0141/strata.exe')
    cfg['env'].update({'STRATA_STAGE_PIN':'0', **env})
    save(label+'-base.json', cfg)

old_fixture = json.loads((OLD/'fixture.json').read_text(encoding='utf-8'))
save('sessions-fixture.json', old_fixture)
by_key = {r['key']:r for r in old_fixture}


def records(name, n, indexes):
    rows = '\n'.join(f'Record {i}: code=K{i:04d}; stock={(i*17+3)%97}.' for i in range(n))
    request = dict(model='qwen3.8-flash-next', messages=[dict(role='user', content=rows +
        '\nReturn only a JSON array of stock values for records ' + ', '.join(map(str, indexes)) + ', in that order.')],
        temperature=0, max_tokens=96, stream=True, chat_template_kwargs={'enable_thinking':False})
    return dict(key=name, request=request, expected=[(i*17+3)%97 for i in indexes], pin=None)


cases = [records('records-small', 20, (7,13,19)), records('records-medium', 44, (7,23,31,38,43)),
         dict(copy.deepcopy(by_key['prefix-0']), key='source-2k'),
         dict(copy.deepcopy(by_key['B0']), key='source-3k5'),
         records('records-5k', 260, (7,23,51,88,99))]
fixture = [dict(copy.deepcopy(by_key['warm']), group='warm')]
for round_i in range(2):
    for row in (cases if round_i == 0 else list(reversed(cases))):
        case = copy.deepcopy(row)
        case.update(key=f'{row["key"]}-r{round_i+1}', group='cold', pin=None)
        # Different system text near the beginning prevents all cross-request prefix reuse.
        messages = case['request']['messages']
        tag = f'Document task {case["key"]}. '
        if messages[0]['role'] == 'system':
            messages[0]['content'] = tag + messages[0]['content']
        else:
            messages.insert(0, dict(role='system', content=tag+'Return only the requested JSON.'))
        case['request'].pop('strata_prefix', None)
        fixture.append(case)
save('prefill-fixture.json', fixture)
shutil.copyfile(ROOT/'bench/results/2026-10-04-windows-mapped-release/monitor_windows.py', OUT/'monitor_windows.py')
save('fixture-manifest.json', dict(prefill_sha256=sha(OUT/'prefill-fixture.json'),
    sessions_sha256=sha(OUT/'sessions-fixture.json'), requests=len(fixture),
    cases=[dict(key=c['key'], expected=c['expected']) for c in fixture]))
print(json.dumps(dict(requests=len(fixture), fixture_sha256=sha(OUT/'prefill-fixture.json'))))
