"""Install the measured executable and configs, keeping exact rollback copies."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source_commit', help='Full commit id of the engine patch that was built and tested')
opts = parser.parse_args()
assert len(opts.source_commit) == 40 and all(c in '0123456789abcdef' for c in opts.source_commit)
out = Path(__file__).resolve().parent
candidate = out / 'mapped-output/strata.exe'
expected_exe = '38ad7934bb1e3cbbe29a3bcd1da5d749a648c51de5b4dc628dc52a6212f7d0b8'
assert sha(candidate) == expected_exe
for label in ('mapped-output-a', 'mapped-output-b', 'combined-a', 'mapped-control-b',
              'mapped-copy-fallback', 'general-control', 'general-mapped'):
    result = json.loads((out / (label + '-result.json')).read_text(encoding='utf-8'))
    assert result['ok'] and not result.get('error'), label
    assert len(result['requests']) == result['expected_requests'], label
    assert all(r['valid'] for r in result['requests']), label

model_dir = Path('C:/strata-models')
stable = Path('E:/strata-setup/part2-mapped-output-20261008')
old_exe = Path('E:/strata-setup/part2-helper-resident/strata.exe')
assert sha(old_exe) == '7e5f2d45b92b888e910954b3a9b03ac758872cedd8645764af6cf1626ee141b9'
protected = {
    model_dir / 'strata-256k-int8.json': '943eb8db5f3da2e53d23382a799c524ca640dbb65aa553aa10db636bc0cfd397',
    model_dir / 'strata-dual-p100-coding.shared-settings.json': 'bd9bcf34da7484152e18d97a3436ce50dd771c8766cbf5c4ef2cc6fc6efe9682',
    model_dir / 'strata-dual-p100-experimental.json': '360ed3d01dea155e6280b99ef10b672ff9389b94bdda89fa0fee70960d7bfc21',
}
assert all(sha(p) == digest for p, digest in protected.items())
configs = [
    ('coding', 'strata-dual-p100-coding.json', 'e0383c419379d91536156f10dae82d9e87d8c6c32d9fbf94c1723a5f76adb85c', 'combined-a'),
]
updates = []
for kind, filename, original_hash, label in configs:
    path = model_dir / filename
    assert sha(path) == original_hash, path
    config = json.loads(path.read_text(encoding='utf-8'))
    if kind == 'coding':
        config['args'][config['args'].index('--short-read') + 1] = '1024'
    config.update(exe=str(stable / 'strata.exe'), cwd=str(stable),
                  log=str(stable / ('coding-engine.log' if kind == 'coding' else 'engine.log')))
    tested = json.loads((out / (label + '-config.json')).read_text(encoding='utf-8'))
    ignored = {'exe', 'cwd', 'log'}
    assert {k: v for k, v in config.items() if k not in ignored} == {k: v for k, v in tested.items() if k not in ignored}
    rollback = out / ('rollback-' + kind + '-config.json')
    assert not rollback.exists() or sha(rollback) == original_hash
    shutil.copy2(path, rollback)
    updates.append((kind, path, config))

stable.mkdir(parents=True, exist_ok=True)
target = stable / 'strata.exe'
assert not target.exists() or sha(target) == expected_exe
shutil.copy2(candidate, target)
assert sha(target) == expected_exe
general = model_dir / 'strata-dual-p100-experimental.json'
for filename in ('rollback-general-config.json', 'installed-general-config.json'):
    snapshot = out / filename
    assert not snapshot.exists() or sha(snapshot) == sha(general)
    shutil.copy2(general, snapshot)
installed = {'general': dict(path=str(general), sha256=sha(general), action='retained original engine; no measured general speedup')}
for kind, path, config in updates:
    temporary = path.with_suffix('.mapped-output-next.json')
    assert not temporary.exists(), temporary
    temporary.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)
    shutil.copy2(path, out / ('installed-' + kind + '-config.json'))
    installed[kind] = dict(path=str(path), sha256=sha(path))
assert all(sha(p) == digest for p, digest in protected.items())
receipt = dict(engine_source_commit=opts.source_commit, executable=str(target), executable_sha256=sha(target),
               rollback_executable=str(old_exe), rollback_executable_sha256=sha(old_exe), configs=installed,
               protected_files={str(p): digest for p, digest in protected.items()})
(out / 'install-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print(json.dumps(receipt, indent=2))
