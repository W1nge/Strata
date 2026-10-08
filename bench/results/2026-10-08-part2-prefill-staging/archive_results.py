"""Archive complete measurements; gzip larger logs without changing their original bytes."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

RAW = Path(__file__).resolve().parent
REPO = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr')
DEST = REPO / 'bench/results/2026-10-08-part2-prefill-staging'

def digest(data):
    return hashlib.sha256(data).hexdigest()

summary = json.loads((RAW / 'final-summary.json').read_text(encoding='utf-8'))
install = json.loads((RAW / 'install-receipt.json').read_text(encoding='utf-8'))
assert all(row['ok'] for label, row in summary['runs'].items() if label!='trace-a')
assert not summary['runs']['trace-a']['ok']
assert not DEST.exists(), 'Inspect an existing archive before changing it.'
DEST.mkdir(parents=True)
(DEST / '.gitattributes').write_text('* -text -whitespace\n*.gz binary\n', encoding='utf-8')
files = {}
skip = {'summary.json', 'summary-output.jsonl', 'summarize.py'}
for source in sorted(RAW.iterdir()):
    if not source.is_file() or source.name in skip or source.suffix not in {'.json', '.jsonl', '.log', '.py', '.bat', '.patch'}:
        continue
    original = source.read_bytes()
    compress = source.suffix=='.jsonl' or (source.suffix=='.log' and len(original)>250000)
    name = source.name + ('.gz' if compress else '')
    stored = gzip.compress(original, mtime=0) if compress else original
    target = DEST / name
    target.write_bytes(stored)
    restored = gzip.decompress(target.read_bytes()) if compress else target.read_bytes()
    assert restored == original
    files[name] = dict(bytes=len(stored), sha256=digest(stored), source_name=source.name,
                       original_bytes=len(original), original_sha256=digest(original), gzip=compress)

receipt = dict(raw_directory=str(RAW), engine_source_commit=install['engine_source_commit'],
    upstream_commit=install['upstream_commit'],
    upstream_patch_commit=subprocess.check_output(['git','rev-parse','codex/windows-prefill-staging-release'], cwd=REPO, text=True).strip(),
    hardware=dict(cpu='Intel Core i7-13850HX', ram_gib=32, gpu0='RTX 2080 Ti 22 GiB / 310 W',
                  gpu1='Tesla P100 16 GiB / 250 W', driver='537.13', os='Windows WDDM', p2p=False),
    build=dict(cuda='12.4.131', architectures=['60-real','75-real'], experimental_sm60=True),
    counts={key:summary[key] for key in ('starts','responses','valid_responses','successful_starts')},
    interpretation='The repeatable staging-patch benefit is available RAM. Timing improvement was not consistent in the reversed comparison, and measured physical SSD reads increased. Pascal cache changes belong to upstream.',
    limitations=['trace-a failed with extra GPU timing; not a performance baseline',
                 'pdl_parity exited at cudaGraphGetEdges_v2 on driver 537.13; driver 12020/runtime 12040 API probe retained',
                 'Single Windows machine, one model, finite functional code checks, no broad quality or cross-platform claim'],
    installed=install, files=files)
(DEST / 'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(archive=str(DEST), files=len(files), bytes=sum(f['bytes'] for f in files.values()), counts=receipt['counts']), indent=2))
