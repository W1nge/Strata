"""Install only the tested coding configuration, keeping byte-exact rollback files."""
import hashlib
import json
import os
from pathlib import Path
import time

import psutil

OUT = Path(__file__).resolve().parent
LIVE = Path('C:/strata-models/strata-dual-p100-coding.json')
GENERAL = Path('C:/strata-models/strata-dual-p100-experimental.json')
SINGLE = Path('C:/strata-models/strata-256k-int8.json')
AUDIT = Path('C:/Users/Winge/.zcode/workspace/default/Strata/docs/performance/UPSTREAM-OPTIMIZATION-AUDIT-2026-10-08.md')
EXPECTED = {
    LIVE: 'b19b73a7a75f3fc00a139354359ae1cca3ac38b72413b49a337f9fbfaafa322d',
    GENERAL: '360ed3d01dea155e6280b99ef10b672ff9389b94bdda89fa0fee70960d7bfc21',
    SINGLE: '943eb8db5f3da2e53d23382a799c524ca640dbb65aa553aa10db636bc0cfd397',
    AUDIT: 'd59c6e2b2f686b45ff46574667bf0ee2425b5a6b1a930cca381e15d0d03d184a',
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

assert not (OUT / 'install-receipt.json').exists(), 'Installation already has a receipt.'
for process in psutil.process_iter(['name', 'pid']):
    assert (process.info['name'] or '').lower() not in {'strata.exe', 'ninja.exe', 'nvcc.exe'}, process.info
for path, expected in EXPECTED.items():
    assert sha(path) == expected, f'Changed since baseline: {path}'

for label, expected in [('01404-coding-a', 12), ('01404-general-a', 18), ('01404-short448-a', 4)]:
    result = json.loads((OUT / (label + '-result.json')).read_text(encoding='utf-8'))
    assert result['ok'] and len(result['requests']) == result['expected_requests'] == expected
    assert all(r['valid'] and r['response']['choices'][0]['finish_reason'] == 'stop' for r in result['requests'])

build = json.loads((OUT / 'prefill-release-01404-build.json').read_text(encoding='utf-8'))
exe = Path(build['candidate_exe'])
assert sha(exe) == build['candidate_sha256']
old = json.loads(LIVE.read_text(encoding='utf-8'))
old_exe = Path(old['exe'])
assert sha(old_exe) == '38ad7934bb1e3cbbe29a3bcd1da5d749a648c51de5b4dc628dc52a6212f7d0b8'
for source, name in [(LIVE, 'rollback-coding-config.json'), (GENERAL, 'preserved-general-config.json'),
                     (SINGLE, 'preserved-single-config.json')]:
    with (OUT / name).open('xb') as stream:
        stream.write(source.read_bytes())
new = dict(old)
new['exe'] = str(exe).replace('\\', '/')
new['env'] = dict(old.get('env', {}), STRATA_FILE_RELEASE='1')
tested = json.loads((OUT / '01404-coding-a-config.json').read_text(encoding='utf-8'))
assert {k:v for k,v in new.items() if k!='log'} == {k:v for k,v in tested.items() if k!='log'}
contents = (json.dumps(new, indent=2)+'\n').encode('utf-8')
temporary = LIVE.with_name(LIVE.name + '.prefill-01404.tmp')
with temporary.open('xb') as stream:
    stream.write(contents)
os.replace(temporary, LIVE)
assert LIVE.read_bytes() == contents
(OUT / 'installed-coding-config.json').write_bytes(contents)
for path in (GENERAL, SINGLE, AUDIT):
    assert sha(path) == EXPECTED[path]

receipt = dict(installed_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    engine_source_commit=build['head'], upstream_commit=build['upstream'],
    exe=str(exe), exe_sha256=sha(exe), live_config=str(LIVE), installed_config_sha256=sha(LIVE),
    original_config_sha256=EXPECTED[LIVE], rollback_config=str(OUT / 'rollback-coding-config.json'),
    rollback_exe=str(old_exe), rollback_exe_sha256=sha(old_exe),
    changes=dict(exe=new['exe'], env=dict(STRATA_FILE_RELEASE='1')),
    preserved=[dict(path=str(p), sha256=sha(p)) for p in (GENERAL, SINGLE, AUDIT)],
    no_background_model=True, daily_launcher='C:/strata-models/run-iq3xxs-dual-p100-coding.bat')
(OUT / 'install-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
print(json.dumps(receipt, indent=2))
