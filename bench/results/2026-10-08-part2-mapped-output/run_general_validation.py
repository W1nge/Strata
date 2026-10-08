"""Run the same general workloads serially on the original and candidate engines."""
import json
from pathlib import Path
import subprocess
import sys

repo = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr')
out = Path(__file__).resolve().parent
for label, overrides in [
    ('general-control', {}),
    ('general-mapped', {'exe': str(out / 'mapped-output/strata.exe')}),
]:
    print('START', label, flush=True)
    command = [sys.executable, '-X', 'utf8', str(repo / 'tools/bench_part2_tuning.py'), label,
               '--config', 'C:/strata-models/strata-dual-p100-experimental.json',
               '--out', str(out), '--extended', '--medium', '--rounds', '2',
               '--overrides', json.dumps(overrides)]
    completed = subprocess.run(command, cwd=repo)
    path = out / (label + '-result.json')
    if not path.exists():
        raise SystemExit('No result: ' + label)
    data = json.loads(path.read_text(encoding='utf-8'))
    if not data.get('ok') or data.get('error') or len(data['requests']) != data['expected_requests']:
        raise SystemExit('Incomplete or invalid result; inspect before continuing: ' + label)
    if completed.returncode:
        raise SystemExit(completed.returncode)
