"""Archive the 2026-10-09 prefill short-read / small-chunk runs into the fork's bench tree.

Run it on the measurement host: it copies the runner's daily outputs into this directory
(name + `.gz` for logs and large JSON), then rewrites manifest.json from what is on disk, so
the manifest can be re-derived from the archive alone.
"""
import gzip, hashlib, json
from pathlib import Path

OUT = Path('E:/strata-setup/part2-prefill-helper-source-20261009')
DEST = Path(__file__).resolve().parent

RUNS = ['s768-full', 'bl-768-mf', 'lend-mf-768', 'big-first-768', 'cross-win-a', 'cross6-a', 'cross3-mix-a',
        'sr64-warm192', 'smallseg2-sr32', 'tinyseg-sr0', 't29-sr0',
        'allbatch-192first', 'allbatch-320first', 'allbatch-884first',
        'allbatch-trace-192first', 'allbatch-noshare-192first', 'cross-batch-a', 'cross-batch-base']
SUFFIX = ['-config.json', '-engine.log', '-server.log', '-memory.jsonl', '-result.json']
CONFIGS = ['candidate-shortread768-config.json', 'candidate-shortread256-config.json', 'candidate-shortread64-config.json',
           'candidate-shortread32-trace-config.json', 'candidate-allbatched-config.json', 'candidate-allbatch-trace-config.json',
           'candidate-allbatch-noshare-config.json', 'candidate-allwindows-config.json', 'baseline-shortread768-config.json',
           'candidate-config.json', 'baseline-config.json']
FIXTURES = ['prefill-fixture.json', 'lend-medium-first-fixture.json', 'big-first-fixture.json', 's192-first-fixture.json',
            's320-first-fixture.json', 'small-seg2-fixture.json', 'tiny-seg-fixture.json', 't29-fixture.json',
            'warm-then-192-fixture.json', 'crossover-fixture.json', 'crossover6-fixture.json']
TOOLS = ['run_requests.py', 'summarize.py', 'monitor_windows.py']

names = list(dict.fromkeys([r + s for r in RUNS for s in SUFFIX] + CONFIGS + FIXTURES + TOOLS))
(DEST / '.gitattributes').write_text('* binary\n', encoding='utf-8')
for name in names:
    src = OUT / name
    if not src.is_file():
        raise SystemExit('missing ' + name)
    data = src.read_bytes()
    compressed = src.suffix in ('.jsonl', '.log') or (src.suffix == '.json' and len(data) > 120000)
    dst = DEST / (name + ('.gz' if compressed else ''))
    stored = gzip.compress(data, mtime=0) if compressed else data
    dst.write_bytes(stored)
    assert (gzip.decompress(dst.read_bytes()) if compressed else dst.read_bytes()) == data

files = []
for path in sorted(DEST.iterdir()):
    if path.name in ('manifest.json', 'RESULTS.md', '.gitattributes'):
        continue
    stored = path.read_bytes()
    raw = gzip.decompress(stored) if path.suffix == '.gz' else stored
    files.append(dict(source=path.name[:-3] if path.suffix == '.gz' else path.name, archived=path.name,
                      bytes=len(raw), stored_bytes=len(stored),
                      sha256=hashlib.sha256(raw).hexdigest(), stored_sha256=hashlib.sha256(stored).hexdigest()))
(DEST / 'manifest.json').write_text(json.dumps(files, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(path=str(DEST), files=len(files), stored=sum(f['stored_bytes'] for f in files),
                      raw=sum(f['bytes'] for f in files))))

