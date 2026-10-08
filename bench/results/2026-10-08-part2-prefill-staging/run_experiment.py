"""Run a single bounded prefill experiment with the repository's verified corpus."""
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import runpy

import psutil

ROOT = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr')
OUT = Path(__file__).resolve().parent
BASE = OUT / 'baseline-coding-config.json'
LIVE = Path('C:/strata-models/strata-dual-p100-coding.json')

if not BASE.exists():
    BASE.write_bytes(LIVE.read_bytes())

label = sys.argv[1]
overrides = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
command = [sys.executable, '-X', 'utf8', str(ROOT / 'tools/bench_part2_tuning.py'),
           label, '--config', str(BASE), '--out', str(OUT)]
command += sys.argv[3:] or ['--extended', '--medium']
command += ['--rounds', '2', '--overrides', json.dumps(overrides)]
receipt = OUT / (label + '-command.json')
if receipt.exists():
    raise SystemExit('Use a new label: ' + label)
receipt.write_text(json.dumps(command, indent=2), encoding='utf-8')
monitor = runpy.run_path(str(ROOT / 'bench/results/2026-10-04-windows-mapped-release/monitor_windows.py'))
process = subprocess.Popen(command, cwd=ROOT)
stopped = threading.Event()


def sample_memory():
    owner = psutil.Process(process.pid)
    with (OUT / (label + '-memory.jsonl')).open('x', encoding='utf-8') as stream:
        while not stopped.is_set():
            try:
                entry = monitor['sample'](owner)
                result_path = OUT / (label + '-result.json')
                try:
                    progress = json.loads(result_path.read_text(encoding='utf-8'))
                    entry['completed_requests'] = len(progress['requests'])
                    entry['last_request'] = progress['requests'][-1]['key'] if progress['requests'] else None
                except (FileNotFoundError, json.JSONDecodeError):
                    entry['completed_requests'] = 0
                stream.write(json.dumps(entry) + '\n')
                stream.flush()
            except Exception as error:
                stream.write(json.dumps({'epoch_s': time.time(), 'error': repr(error)}) + '\n')
                stream.flush()
            stopped.wait(1)


thread = threading.Thread(target=sample_memory, daemon=True)
thread.start()
try:
    code = process.wait()
finally:
    stopped.set()
    thread.join(timeout=10)
raise SystemExit(code)
