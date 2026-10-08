"""Run numeric checks serially on each physical GPU with the pinned CUDA runtime."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

OUT = Path(__file__).resolve().parent
BUILD = Path('E:/strata-setup/part2-dual/build')
MODEL = 'C:/strata-models/hf/IQ3_XXS/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf'
tests = [('mmvq_multi_parity', []), ('pdl_parity', []),
         ('native_expert_parity', [MODEL, '0', '1', '8', '12'])]
results = []
for device in ('0', '1'):
    for name, args in tests:
        executable = BUILD / (name + '.exe')
        log = OUT / ('01404-gpu' + device + '-' + name + '.log')
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=device)
        env['PATH'] = 'E:/strata-setup/cuda-portable/bin;' + env.get('PATH', '')
        start = time.monotonic()
        with log.open('x', encoding='utf-8') as stream:
            result = subprocess.run([str(executable), *args], env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=180)
        entry = dict(device=device, name=name, args=args, returncode=result.returncode,
                     seconds=time.monotonic()-start, log=str(log),
                     executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest())
        results.append(entry)
        (OUT / '01404-gpu-tests.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(json.dumps(entry), flush=True)
raise SystemExit(0 if all(row['returncode'] == 0 for row in results) else 1)
