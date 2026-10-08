"""Preserve the final candidate and diagnose the retained-driver CUDA API limit."""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

OUT = Path(__file__).resolve().parent
ROOT = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr')
BUILD = Path('E:/strata-setup/part2-dual/build')
BIN = Path('E:/strata-setup/cuda-portable/bin')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

destination = OUT / 'prefill-release-01404'
destination.mkdir(exist_ok=False)
candidate = destination / 'strata.exe'
shutil.copy2(BUILD / 'strata.exe', candidate)
record = dict(
    head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    upstream=subprocess.check_output(['git', 'rev-parse', 'upstream/main'], cwd=ROOT, text=True).strip(),
    candidate_exe=str(candidate), candidate_sha256=sha(candidate),
    source_sha256=sha(ROOT / 'src/prefill/prefill.cpp'),
    cmake_cache_sha256=sha(BUILD / 'CMakeCache.txt'),
    build_log_sha256=sha(OUT / 'build-upstream-01404.log'),
    driver=subprocess.check_output(['nvidia-smi', '--query-gpu=index,name,driver_version,power.limit,memory.total',
                                   '--format=csv,noheader'], text=True).strip().splitlines())
(OUT / 'prefill-release-01404-build.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps(record), flush=True)

# Both test failures occur in cudaGraphGetEdges_v2, before any graph replay.
# Probe the legacy and new count-only APIs on the very same empty graph.
with os.add_dll_directory(str(BIN)):
    runtime = C.WinDLL(str(BIN / 'cudart64_12.dll'))
    driver, version = C.c_int(), C.c_int()
    assert runtime.cudaDriverGetVersion(C.byref(driver)) == 0
    assert runtime.cudaRuntimeGetVersion(C.byref(version)) == 0
    graph = C.c_void_p()
    created = runtime.cudaGraphCreate(C.byref(graph), C.c_uint(0))
    assert created == 0, created
    count_v1, count_v2 = C.c_size_t(), C.c_size_t()
    legacy = runtime.cudaGraphGetEdges(graph, None, None, C.byref(count_v1))
    extended = runtime.cudaGraphGetEdges_v2(graph, None, None, None, C.byref(count_v2))
    runtime.cudaGetErrorString.restype = C.c_char_p
    probe = dict(driver_version=driver.value, runtime_version=version.value,
                 graph_create=created,
                 legacy_count=dict(code=legacy, message=runtime.cudaGetErrorString(legacy).decode(), count=count_v1.value),
                 v2_count=dict(code=extended, message=runtime.cudaGetErrorString(extended).decode(), count=count_v2.value))
    assert runtime.cudaGraphDestroy(graph) == 0
(OUT / '01404-graph-api-probe.json').write_text(json.dumps(probe, indent=2), encoding='utf-8')
print(json.dumps(probe), flush=True)

results = []
for release in ('0', '1'):
    name = '01404-source-release-' + release
    env = dict(os.environ, STRATA_FILE_RELEASE=release, CUDA_VISIBLE_DEVICES='0')
    env['PATH'] = str(BIN) + ';' + env.get('PATH', '')
    command = [str(BUILD / 'file_expert_source_test.exe'), '--rotation-gpu']
    start = time.monotonic()
    with (OUT / (name + '.log')).open('x', encoding='utf-8') as log:
        result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    row = dict(name=name, command=command, returncode=result.returncode, seconds=time.monotonic()-start,
               executable_sha256=sha(Path(command[0])))
    results.append(row)
    print(json.dumps(row), flush=True)
(OUT / '01404-source-tests.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
raise SystemExit(0 if all(r['returncode'] == 0 for r in results) else 1)
