import json
from pathlib import Path
import subprocess
import sys

repo = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr')
out = Path('E:/strata-setup/part2-coding-next')
for label, overrides, extra, rounds in json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')):
    print('START', label, flush=True)
    command = [sys.executable, '-X', 'utf8', str(repo/'tools/bench_part2_tuning.py'), label,
               '--config', 'C:/strata-models/strata-dual-p100-coding.json', '--out', str(out),
               '--coding', '--rounds', str(rounds), '--overrides', json.dumps(overrides), *extra]
    completed = subprocess.run(command, cwd=repo)
    path = out/(label+'-result.json')
    if not path.exists():
        raise SystemExit('No result; inspect logs before continuing: '+label)
    result = json.loads(path.read_text(encoding='utf-8'))
    if result.get('error') or len(result['requests']) != result['expected_requests']:
        raise SystemExit('Incomplete run; inspect logs before continuing: '+label)
    if completed.returncode:
        print('Functional failure retained for comparison:', label, flush=True)
