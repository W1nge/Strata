"""Archive this experiment, excluding executables/worktrees, with byte-level checksums."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

SRC=Path(__file__).resolve().parent
REPO=Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr')
DEST=REPO/'bench/results/2026-10-08-part2-shared-prefix'
def sha(data):
    return hashlib.sha256(data).hexdigest()
if DEST.exists():
    raise SystemExit('Archive already exists; preserve it')
DEST.mkdir(parents=True)
(DEST/'.gitattributes').write_text('* -text\n',encoding='utf-8')
patch=subprocess.check_output(['git','show','--format=','--binary','99bed00de0201fa6a484cf3a3b3b18a169702191'],cwd=REPO)
(SRC/'shared-prefix-pin.patch').write_bytes(patch)
manifest=[]
for path in sorted(SRC.iterdir()):
    if not path.is_file() or path.suffix not in ('.py','.json','.jsonl','.log','.bat','.md','.patch'):
        continue
    if path.name in ('summary-console.json',):
        continue
    raw=path.read_bytes()
    compressed=len(raw)>128*1024
    target=DEST/(path.name+('.gz' if compressed else ''))
    stored=gzip.compress(raw,compresslevel=9,mtime=0) if compressed else raw
    target.write_bytes(stored)
    assert (gzip.decompress(target.read_bytes()) if compressed else target.read_bytes())==raw
    manifest.append(dict(source=path.name,path=target.name,raw_bytes=len(raw),stored_bytes=len(stored),
                         raw_sha256=sha(raw),stored_sha256=sha(stored)))
receipt=dict(source_commit='99bed00de0201fa6a484cf3a3b3b18a169702191',
             upstream_base='6674a0065fb96bacde33e3eb10f91a1df86f95f2',
             upstream_pr_head='7a8f2b292255c089322f3ef97cc4fc5117229e52',
             files=manifest,stored_bytes=sum(r['stored_bytes'] for r in manifest))
(DEST/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(dict(files=len(manifest),stored_bytes=receipt['stored_bytes'],path=str(DEST))))
