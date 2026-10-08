"""Archive one completed run without model binaries or unrelated workspace files."""
import gzip
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
DEST = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr/bench/results/2026-10-09-part2-prefill-0141')
if DEST.exists():
    raise SystemExit('Archive already exists; preserve it')
DEST.mkdir(parents=True)
(DEST/'.gitattributes').write_text('* binary\n', encoding='utf-8')
files = []
for src in sorted(OUT.iterdir()):
    if not src.is_file() or src.suffix not in ('.py','.md','.json','.jsonl','.log','.bat','.patch'):
        continue
    if src.name.endswith('-console.json'):
        continue
    data = src.read_bytes()
    compressed = src.suffix in ('.jsonl','.log') or (src.suffix == '.json' and len(data) > 120000)
    stored = gzip.compress(data,mtime=0) if compressed else data
    dst = DEST/(src.name+('.gz' if compressed else ''))
    dst.write_bytes(stored)
    assert (gzip.decompress(dst.read_bytes()) if compressed else dst.read_bytes()) == data
    files.append(dict(source=src.name, archived=dst.name, bytes=len(data), stored_bytes=len(stored),
        sha256=hashlib.sha256(data).hexdigest(), stored_sha256=hashlib.sha256(stored).hexdigest()))
(DEST/'manifest.json').write_text(json.dumps(files,indent=2),encoding='utf-8')
print(json.dumps(dict(path=str(DEST), files=len(files), bytes=sum(f['stored_bytes'] for f in files))))
