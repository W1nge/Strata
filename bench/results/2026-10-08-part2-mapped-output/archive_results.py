"""Copy complete measurements byte-for-byte into the integration repository."""
import hashlib
import json
from pathlib import Path
import shutil


raw = Path(__file__).resolve().parent
repo = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr')
dest = repo / 'bench/results/2026-10-08-part2-mapped-output'
summary = json.loads((raw / 'summary.json').read_text(encoding='utf-8'))
install = json.loads((raw / 'install-receipt.json').read_text(encoding='utf-8'))
assert not summary['pending'] and summary['responses'] == summary['valid_responses']
assert len(summary['runs']) == 13 and summary['responses'] == 137
assert all(v['all_finish_reasons_stop'] for v in summary['runs'].values())
assert not dest.exists(), 'Archive exists; inspect it before changing evidence.'
dest.mkdir(parents=True)
(dest / '.gitattributes').write_text('*.json -text -whitespace\n*.log -text -whitespace\n*.bat -text -whitespace\n*.py -text -whitespace\n*.patch -text -whitespace\n', encoding='utf-8')
paths = set()
for label in summary['runs']:
    for suffix in ('-config.json', '-result.json', '-engine.log', '-server.log'):
        paths.add(raw / (label + suffix))
paths.update(raw.glob('*-plan.json'))
for filename in ('summary.json', 'summarize.py', 'build-mapped-output.bat', 'build-mapped-output.log',
                 'mapped-output.patch', 'mapped-output-build.json', 'fixture-checks.log',
                 'run_general_validation.py', 'install_mapped_output.py', 'archive_results.py', 'install-receipt.json',
                 'rollback-coding-config.json', 'rollback-general-config.json',
                 'installed-coding-config.json', 'installed-general-config.json', 'final-local-checks.json'):
    paths.add(raw / filename)
paths.add(Path('C:/Users/Winge/Documents/Playground/run_coding_next.py'))
files = {}
for source in sorted(paths):
    target = dest / source.name
    assert source.is_file() and not target.exists(), source
    shutil.copy2(source, target)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    files[source.name] = dict(bytes=source.stat().st_size, sha256=digest)
receipt = dict(engine_source_commit=install['engine_source_commit'],
    upstream_patch_commit='2edbb0535633bd9a78f899286b57b831e2381bf1',
    upstream_base='d5ea7133741e67743c0e886bb426c0ce8d69cf6c',
    raw_directory=str(raw),
    hardware=dict(cpu='Intel Core i7-13850HX', ram_gib=32, gpu0='RTX 2080 Ti 22 GiB, 310 W',
                  gpu1='Tesla P100 16 GiB, 250 W', driver='537.13', os='Windows WDDM', p2p=False),
    build=dict(cuda='12.4.131', architecture=['60-real', '75-real'], experimental_sm60=True),
    validation=dict(model_starts=len(summary['runs']), responses=summary['responses'],
                    core_responses=summary['core_responses'], editing_responses=summary['editing_responses'],
                    probe_responses=summary['probe_responses'], general_responses=36,
                    all_functional_checks_passed=True, all_finish_reasons_stop=True),
    decision='Install mapped reduced helper output and short-read 1024 only in coding for more consistent first-edit latency. Retain the original general engine and threshold 448: general request time was flat and decode throughput was 2.15% lower in its one paired comparison. Keep suffix draft 0, original expert profile, CPU pool defaults and 1024 MiB VRAM reserve.',
    installed=install, files=files)
(dest / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(archive=str(dest), files=len(files), responses=summary['responses']), indent=2))
