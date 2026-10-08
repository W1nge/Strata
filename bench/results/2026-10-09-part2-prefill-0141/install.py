"""Install only after all bounded validations and the daily source synchronization pass."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

import psutil

OUT = Path(__file__).resolve().parent
ROOT = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr')
DAILY = Path('C:/Users/Winge/.zcode/workspace/default/Strata')
LIVE = Path('C:/strata-models/strata-dual-p100-coding.json')
AUDIT = DAILY/'docs/performance/UPSTREAM-OPTIMIZATION-AUDIT-2026-10-08.md'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


pre = json.loads((OUT/'preflight.json').read_text(encoding='utf-8'))
cold = json.loads((OUT/'cold-summary.json').read_text(encoding='utf-8'))
reg = json.loads((OUT/'regression-summary.json').read_text(encoding='utf-8'))
verification = json.loads((OUT/'verification-receipt.json').read_text(encoding='utf-8'))
assert verification['server_exit_code'] == 0 and verification['core_ctest_passed'] == 2
assert len(cold['runs']) == 7 and all(v['ok'] and v['all_cold_cache_misses'] for v in cold['runs'].values())
assert all(v['requests_identical'] and v['answers_identical'] and v['token_counts_identical']
           for v in cold['comparison'].values())
assert reg['sessions']['valid'] == 17 and reg['sessions']['return_hits'] == 8
assert reg['coding']['valid'] == 6 and not reg['coding']['different_answers']
assert sha(LIVE) == pre['baseline_config_sha256'], 'The live configuration changed during the experiment'
assert sha(AUDIT) == pre['audit_sha256'], 'The user audit edit changed; preserve it'
assert sha(OUT/'rollback-coding-config.json') == sha(LIVE)
for p in psutil.process_iter(['name']):
    assert (p.info['name'] or '').lower() not in ('strata.exe','nvcc.exe','cmake.exe'), 'A model/build is still running'
for name in ('serve/server.py','tools/strata_tokenizer.py','src/prefill/prefill.cpp',
             'src/program/generate.cpp','src/core/expert_source.cpp','include/strata/core/conversation_cache.hpp'):
    assert sha(ROOT/name) == sha(DAILY/name), 'Daily source differs: '+name
cfg = json.loads((OUT/'v141-direct-base.json').read_text(encoding='utf-8'))
assert sha(Path(cfg['exe'])) == cold['runs']['v141-direct-b']['exe_sha256']
cfg['log'] = str(OUT/'daily-coding-engine.log')
data = (json.dumps(cfg,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
candidate = OUT/'installed-coding-config.json'
assert not candidate.exists(), 'Installation already recorded'
candidate.write_bytes(data)
staged = LIVE.with_name(LIVE.name+'.prefill-0141-new')
with staged.open('xb') as f:
    f.write(data)
staged.replace(LIVE)
assert LIVE.read_bytes() == data
receipt = dict(epoch=time.time(), config=str(LIVE), old_config_sha256=pre['baseline_config_sha256'],
    config_sha256=sha(LIVE), exe=cfg['exe'], exe_sha256=sha(Path(cfg['exe'])),
    rollback_config=str(OUT/'rollback-coding-config.json'), old_exe_sha256=pre['baseline_exe_sha256'],
    daily_source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=DAILY,text=True).strip(),
    tested_source_commit=pre['merged_commit'], audit_sha256=sha(AUDIT),
    gpu=subprocess.check_output(['nvidia-smi','--query-gpu=index,name,driver_version,power.limit','--format=csv,noheader'],text=True).strip())
(OUT/'installation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=False,indent=2))
