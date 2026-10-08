"""Install exactly the qualified configuration and retain a byte-for-byte rollback."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone, timedelta

OUT=Path(__file__).resolve().parent
LIVE=Path('C:/strata-models/strata-dual-p100-coding.json')
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
if (OUT/'installation.json').exists():
    raise SystemExit('Installation already recorded')
assert sha(LIVE)=='1e1041b39bfc9c51b06b265733a6b84f3183e6affbe81c9c2c3b36c75340c013'
for label in ('fixed-a','fixed-b','coding-final'):
    assert json.loads((OUT/(label+'-result.json')).read_text(encoding='utf-8'))['ok']
assert all(json.loads((OUT/'coding-summary.json').read_text())['same_as_previous_01404'].values())
old=json.loads(LIVE.read_text(encoding='utf-8'))
new=json.loads((OUT/'fixed-b-config.json').read_text(encoding='utf-8'))
new['log']=old['log']
assert {k:v for k,v in old.items() if k not in ('exe','args')} == {k:v for k,v in new.items() if k not in ('exe','args')}
assert sha(Path(new['exe']))=='7722a6d34f8efded911dd0eeef091461972fa5958bf75725767172a3678f2a25'
other=[Path('C:/strata-models/strata-dual-p100-experimental.json'),Path('C:/strata-models/strata-256k-int8.json')]
preserved={str(p):sha(p) for p in other}
backup=OUT/'rollback-coding-config.json'
with backup.open('xb') as stream:
    stream.write(LIVE.read_bytes())
LIVE.write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert json.loads(LIVE.read_text(encoding='utf-8'))==new
assert all(sha(Path(p))==h for p,h in preserved.items())
receipt=dict(installed_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
    config=str(LIVE),before_sha256=sha(backup),after_sha256=sha(LIVE),
    backup=str(backup),exe=new['exe'],exe_sha256=sha(Path(new['exe'])),
    source_commit='99bed00de0201fa6a484cf3a3b3b18a169702191',
    upstream_pr_commit='7a8f2b292255c089322f3ef97cc4fc5117229e52',
    preserved_configs=preserved)
(OUT/'installation.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt,indent=2))
