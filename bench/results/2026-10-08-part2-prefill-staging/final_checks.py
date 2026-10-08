"""Record the installed identities, protected files, source parity, and stopped test service."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

import psutil

OUT = Path(__file__).resolve().parent
REPO = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr')
DAILY = Path('C:/Users/Winge/.zcode/workspace/default/Strata')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args, cwd=REPO):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()

install = json.loads((OUT / 'install-receipt.json').read_text(encoding='utf-8'))
assert sha(Path(install['live_config'])) == install['installed_config_sha256']
assert sha(Path(install['exe'])) == install['exe_sha256']
for item in install['preserved']:
    assert sha(Path(item['path'])) == item['sha256'], item['path']
active = [p.info for p in psutil.process_iter(['name','pid'])
          if (p.info['name'] or '').lower() in {'strata.exe','nvcc.exe','ninja.exe'}]
listeners = [dict(pid=c.pid, address=list(c.laddr)) for c in psutil.net_connections(kind='tcp')
             if c.status==psutil.CONN_LISTEN and c.laddr.port==18997]
assert not active and not listeners, (active, listeners)
diff = git('diff','--name-only','HEAD','codex/daily-upstream-01403','--','src','include','serve','tools','CMakeLists.txt','setup.py')
assert not diff, diff
driver = subprocess.check_output(['nvidia-smi','--query-gpu=index,name,driver_version,power.limit,memory.total','--format=csv,noheader'], text=True).strip().splitlines()
assert len(driver)==2 and all('537.13' in row for row in driver)
assert '310.00 W' in driver[0] and '250.00 W' in driver[1]
patch = subprocess.check_output(['git','diff','--binary','6674a0065fb96bacde33e3eb10f91a1df86f95f2','codex/windows-prefill-staging-release'], cwd=REPO)
(OUT / 'upstream-prefill-release.patch').write_bytes(patch)
record = dict(checked_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
    integration_head=git('rev-parse','HEAD'), daily_head=git('rev-parse','HEAD',cwd=DAILY),
    upstream_patch_commit=git('rev-parse','codex/windows-prefill-staging-release'),
    upstream_patch_sha256=sha(OUT / 'upstream-prefill-release.patch'),
    engine_source_commit=install['engine_source_commit'],
    engine_source_sha256=sha(REPO / 'src/prefill/prefill.cpp'),
    integration_daily_engine_source_equal=True,
    installed_exe_sha256=sha(Path(install['exe'])), installed_config_sha256=sha(Path(install['live_config'])),
    preserved=install['preserved'], gpu=driver, active_model_or_build_processes=active, test_port_listeners=listeners,
    daily_tracked_status=git('status','--porcelain=v1','--untracked-files=no',cwd=DAILY),
    test_harness_sha256=sha(REPO / 'tools/bench_part2_tuning.py'))
(OUT / 'final-local-checks.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record,indent=2))
