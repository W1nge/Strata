"""Run the existing coding regression once with the verified cache configuration."""
import json
from pathlib import Path
import runpy
import subprocess
import sys
import threading
import time

import psutil

ROOT = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr')
OUT = Path(__file__).resolve().parent
label = 'coding-final'
if (OUT/(label+'-command.json')).exists():
    raise SystemExit('This label already exists; preserve the earlier run')
command = [sys.executable, '-X', 'utf8', str(ROOT/'tools/bench_part2_tuning.py'), label,
           '--config', str(OUT/'fixed-b-config.json'), '--out', str(OUT),
           '--coding', '--coding-long', '--coding-edit', '--rounds', '1']
(OUT/(label+'-command.json')).write_text(json.dumps(command,indent=2),encoding='utf-8')
sample = runpy.run_path(str(ROOT/'bench/results/2026-10-04-windows-mapped-release/monitor_windows.py'))['sample']
process = subprocess.Popen(command,cwd=ROOT,creationflags=subprocess.CREATE_NO_WINDOW)
stop = threading.Event()
def monitor():
    owner=psutil.Process(process.pid)
    with (OUT/(label+'-memory.jsonl')).open('x',encoding='utf-8') as stream:
        while not stop.is_set():
            try:
                item=sample(owner)
                try:
                    d=json.loads((OUT/(label+'-result.json')).read_text(encoding='utf-8'))
                    item['completed_requests']=len(d['requests'])
                except (FileNotFoundError,json.JSONDecodeError):
                    item['completed_requests']=0
                stream.write(json.dumps(item)+'\n')
                stream.flush()
            except Exception as error:
                stream.write(json.dumps({'epoch_s':time.time(),'error':repr(error)})+'\n')
            stop.wait(1)
thread=threading.Thread(target=monitor,daemon=True)
thread.start()
try:
    code=process.wait(timeout=930)
except subprocess.TimeoutExpired:
    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
    raise
finally:
    stop.set()
    thread.join(timeout=5)
raise SystemExit(code)
