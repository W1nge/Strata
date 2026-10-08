"""Verify the archive manifest and optionally its staged Git bytes."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent
receipt = json.loads((root / 'receipt.json').read_text(encoding='utf-8'))
for name, entry in receipt['files'].items():
    stored = (root / name).read_bytes()
    assert len(stored)==entry['bytes'] and hashlib.sha256(stored).hexdigest()==entry['sha256'], name
    original = gzip.decompress(stored) if entry['gzip'] else stored
    assert len(original)==entry['original_bytes'] and hashlib.sha256(original).hexdigest()==entry['original_sha256'], name
if '--staged' in sys.argv:
    repo = Path(subprocess.check_output(['git','rev-parse','--show-toplevel'], cwd=root, text=True).strip())
    records = subprocess.check_output(['git','ls-files','--stage','-z','--',str(root)], cwd=repo).decode().split('\0')
    ids = {row.split('\t',1)[1]:row.split()[1] for row in records if row}
    for path in root.iterdir():
        if not path.is_file():
            continue
        data = path.read_bytes()
        expected = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        assert ids[path.relative_to(repo).as_posix()]==expected, f'Git converted {path.name}'
print(json.dumps(dict(archive=str(root), verified_files=len(receipt['files']), staged_bytes_equal='--staged' in sys.argv)))
