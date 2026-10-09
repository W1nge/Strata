"""Archive the prefill-helper-source A/B run into the fork's bench tree."""
import gzip
import hashlib
import json
from pathlib import Path

OUT = Path('E:/strata-setup/part2-prefill-helper-source-20261009')
DEST = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr/bench/results/2026-10-09-prefill-helper-source')

RUNS = ['baseline-a', 'candidate-a', 'diag-timing', 'lend-control', 'lend-shareoff']
SUFFIX = ['-config.json', '-engine.log', '-server.log', '-memory.jsonl', '-result.json']
EXTRA = [
    'run_requests.py', 'summarize.py', 'monitor_windows.py', 'verify_regressions.py',
    'prefill-fixture.json', 'lend-ab-fixture.json', 'prefill-timing-input-fixture.json',
    'baseline-config.json', 'candidate-config.json', 'prefill-timing-input-config.json', 'archive.py',
]

names = []
for run in RUNS:
    for suffix in SUFFIX:
        names.append(run + suffix)
names += EXTRA

DEST.mkdir(parents=True, exist_ok=True)
(DEST / '.gitattributes').write_text('* binary\n', encoding='utf-8')
files = []
for name in names:
    src = OUT / name
    if not src.is_file():
        raise SystemExit('missing ' + name)
    data = src.read_bytes()
    compressed = src.suffix in ('.jsonl', '.log') or (src.suffix == '.json' and len(data) > 120000)
    stored = gzip.compress(data, mtime=0) if compressed else data
    dst = DEST / (name + ('.gz' if compressed else ''))
    dst.write_bytes(stored)
    assert (gzip.decompress(dst.read_bytes()) if compressed else dst.read_bytes()) == data
    files.append(dict(source=name, archived=dst.name, bytes=len(data), stored_bytes=len(stored),
                      sha256=hashlib.sha256(data).hexdigest(), stored_sha256=hashlib.sha256(stored).hexdigest()))
(DEST / 'manifest.json').write_text(json.dumps(files, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(path=str(DEST), files=len(files), bytes=sum(f['stored_bytes'] for f in files),
                      raw_bytes=sum(f['bytes'] for f in files))))

