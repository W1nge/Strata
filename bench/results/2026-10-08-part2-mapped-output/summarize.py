"""Recompute this round from saved responses; --partial permits unfinished live runs."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re


CORE = {'utilities', 'ttl_cache', 'algorithms', 'matrices'}


def metrics(rows):
    timings = [r['response']['timings'] for r in rows]
    tokens = sum(t['predicted_n'] for t in timings)
    decode_ms = sum(t['predicted_ms'] for t in timings)
    return dict(requests=len(rows), output_tokens=tokens, decode_seconds=decode_ms / 1000,
                weighted_tps=tokens * 1000 / decode_ms if decode_ms else None,
                prompt_seconds=sum(t['prompt_ms'] for t in timings) / 1000,
                request_seconds=sum(r['seconds'] for r in rows))


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('root', nargs='?', type=Path, default=Path(__file__).resolve().parent)
parser.add_argument('--partial', action='store_true')
opts = parser.parse_args()
report = dict(runs={}, comparisons=[], responses=0, valid_responses=0, core_responses=0,
              editing_responses=0, probe_responses=0, pending=[])
loaded = {}
for path in sorted(opts.root.glob('*-result.json')):
    data = json.loads(path.read_text(encoding='utf-8'))
    rows = data['requests']
    if not data.get('ok') or data.get('error') or len(rows) != data['expected_requests']:
        if opts.partial:
            report['pending'].append(dict(label=data['label'], completed=len(rows),
                                          expected=data['expected_requests'], error=data.get('error')))
            continue
        raise AssertionError(str(path))
    assert rows and all(r['valid'] for r in rows), path
    report['responses'] += len(rows)
    report['valid_responses'] += sum(r['valid'] for r in rows)
    loaded[data['label']] = rows
    by_case, by_round = defaultdict(list), defaultdict(list)
    for row in rows:
        case = row['key'].split('@')[0]
        by_case[case].append(row)
        if case in CORE:
            by_round[row['key'].split('@')[1] if '@' in row['key'] else '1'].append(row)
        report['core_responses'] += case in CORE
        report['editing_responses'] += case == 'edit_utilities'
        report['probe_responses'] += case == 'probe'
    core = [r for r in rows if r['key'].split('@')[0] in CORE]
    log = (opts.root / (data['label'] + '-engine.log')).read_text(encoding='utf-8')
    helpers = re.findall(r'CUDA1: (\d+) expert entries, (\d+) active layer launches, ([\d.]+) MiB returned .*?host (\d+) ms staging\+launching, (\d+) ms waiting', log)
    file_reads = re.findall(r'resident RAM: .*?, (\d+) blob reads from the file', log)
    assert len(helpers) == len(rows), (path, 'helper counters', len(helpers), len(rows))
    helper_rows = [dict(key=r['key'], entries=int(h[0]), launches=int(h[1]), mib=float(h[2]),
                        begin_ms=int(h[3]), wait_ms=int(h[4])) for r, h in zip(rows, helpers)]
    report['runs'][data['label']] = dict(
        all=metrics(rows), core=metrics(core), cases={k: metrics(v) for k, v in by_case.items()},
        core_rounds={k: metrics(v) for k, v in by_round.items()},
        all_finish_reasons_stop=all(r['response']['choices'][0]['finish_reason'] == 'stop' for r in rows),
        helper=helper_rows, file_blob_reads_cumulative=[int(n) for n in file_reads],
        per_request=[dict(key=r['key'], seconds=r['seconds'], **r['response']['timings']) for r in rows])

pairs = [('baseline-a', 'reserve2048-a'), ('baseline-a', 'cpu-auto-a'),
         ('baseline-a', 'suffix-a'), ('baseline-a', 'mapped-output-a'),
         ('mapped-control-b', 'mapped-output-a'), ('mapped-control-b', 'combined-a'),
         ('mapped-control-b', 'mapped-output-b'),
         ('mapped-control-b', 'mapped-copy-fallback'),
         ('mapped-output-a', 'combined-a'), ('editing-base-a', 'short1024-a'),
         ('general-control', 'general-mapped')]
for base, candidate in pairs:
    if base not in loaded or candidate not in loaded:
        continue
    original = {r['key']: r for r in loaded[base]}
    new = {r['key']: r for r in loaded[candidate]}
    common = original.keys() & new.keys()
    selections = dict(core=sorted(k for k in common if k.split('@')[0] in CORE),
                      editing=sorted(k for k in common if k.startswith('edit_utilities')),
                      all_common=sorted(common))
    groups = {}
    for name, keys in selections.items():
        if not keys:
            continue
        values = [metrics([rr[k] for k in keys]) for rr in (original, new)]
        groups[name] = dict(measurements=values,
            throughput_gain_percent=(values[1]['weighted_tps'] / values[0]['weighted_tps'] - 1) * 100,
            request_time_reduction_percent=(1 - values[1]['request_seconds'] / values[0]['request_seconds']) * 100,
            identical_text=sum(original[k]['response']['choices'][0]['message']['content'] ==
                               new[k]['response']['choices'][0]['message']['content'] for k in keys),
            compared_responses=len(keys))
    report['comparisons'].append(dict(baseline=base, candidate=candidate, groups=groups))

assert loaded, 'no completed results found'
filename = 'summary-progress.json' if opts.partial else 'summary.json'
(opts.root / filename).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(responses=report['responses'], pending=report['pending'],
    runs={k: dict(requests=v['all']['requests'], core_tps=v['core']['weighted_tps'],
                  core_seconds=v['core']['request_seconds'],
                  editing=v['cases'].get('edit_utilities')) for k, v in report['runs'].items()},
    comparisons=[dict(baseline=c['baseline'], candidate=c['candidate'],
                      groups={k: {field: value for field, value in v.items() if field != 'measurements'}
                              for k, v in c['groups'].items()}) for c in report['comparisons']]), indent=2))
