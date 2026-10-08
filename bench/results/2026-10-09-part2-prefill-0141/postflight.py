"""Record the installed identities and idle state without starting a model."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import time

OUT = Path(__file__).resolve().parent
DAILY = Path('C:/Users/Winge/.zcode/workspace/default/Strata')
INTEGRATION = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr')
receipt = json.loads((OUT/'installation.json').read_text(encoding='utf-8'))


def run(args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True, encoding='utf-8', timeout=30).strip()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


identities = {
    'config_sha256': sha(receipt['config']),
    'exe_sha256': sha(receipt['exe']),
    'audit_sha256': sha(DAILY/'docs/performance/UPSTREAM-OPTIMIZATION-AUDIT-2026-10-08.md'),
    'old_config_sha256': sha(receipt['rollback_config']),
}
rollback = json.loads(Path(receipt['rollback_config']).read_text(encoding='utf-8'))
identities['old_exe_sha256'] = sha(rollback['exe'])
assert all(value == receipt[key] for key, value in identities.items()), identities
assert Path(receipt['config']).read_bytes() == (OUT/'installed-coding-config.json').read_bytes()

integration_head = run(['git','rev-parse','HEAD'], INTEGRATION)
daily_head = run(['git','rev-parse','HEAD'], DAILY)
source_paths = ['src','include','serve','tools/strata_tokenizer.py','CMakeLists.txt','setup.py']
source_diff = run(['git','diff',integration_head,'--',*source_paths], DAILY)
assert not source_diff, source_diff
gpu_text = run(['nvidia-smi','--query-gpu=index,name,driver_version,power.limit,memory.total',
                '--format=csv,noheader,nounits'])
gpus = [dict(zip(('index','name','driver','power_w','memory_mib'), [s.strip() for s in row]))
        for row in csv.reader(gpu_text.splitlines())]
assert len(gpus) == 2 and all(g['driver'] == '537.13' for g in gpus), gpus
assert gpus[0]['name'] == 'NVIDIA GeForce RTX 2080 Ti' and float(gpus[0]['power_w']) == 310
assert gpus[1]['name'] == 'Tesla P100-PCIE-16GB' and float(gpus[1]['power_w']) == 250
process_script = r"""$models = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'strata*.exe' } |
    Select-Object ProcessId, ParentProcessId, Name)
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 18997 -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess)
@{strata_processes=$models; listeners_18997=$listeners} | ConvertTo-Json -Depth 4 -Compress
"""
idle = json.loads(run(['powershell.exe','-NoProfile','-Command',process_script]))
assert not idle['strata_processes'] and not idle['listeners_18997'], idle
sync = dict(epoch=time.time(), daily_head=daily_head, integration_head=integration_head,
            source_paths=source_paths, source_diff_empty=True,
            note='The earlier daily-sync.log records merge conflicts; they were resolved in 62a04cc.')
(OUT/'daily-sync-success.json').write_text(json.dumps(sync,indent=2),encoding='utf-8')
result = dict(epoch=time.time(), identities=identities, gpu=gpus, idle=idle, source_sync=sync,
              verification='Read-only postflight; no model, build, installation or driver change.')
(OUT/'postflight.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
