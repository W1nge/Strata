"""Recompute the coding measurements from complete, archived responses."""
import json
from collections import defaultdict
from pathlib import Path
import sys


def metrics(rows):
    tokens = sum(r['response']['timings']['predicted_n'] for r in rows)
    decode_ms = sum(r['response']['timings']['predicted_ms'] for r in rows)
    return dict(requests=len(rows), output_tokens=tokens,
                weighted_tps=tokens * 1000 / decode_ms,
                request_seconds=sum(r['seconds'] for r in rows),
                drafts=sum(r['response']['timings']['draft_n'] for r in rows),
                accepted=sum(r['response']['timings']['draft_n_accepted'] for r in rows))


root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
report = {'runs': {}, 'comparisons': [], 'responses': 0, 'long_responses': 0}
loaded = {}
for path in sorted(root.glob('*-result.json')):
    data = json.loads(path.read_text(encoding='utf-8'))
    rows = data['requests']
    assert data['ok'] and not data.get('error'), path
    assert rows and len(rows) == data.get('expected_requests', len(rows)), path
    assert all(r['valid'] and r['response']['choices'][0]['finish_reason'] == 'stop' for r in rows), path
    report['responses'] += len(rows)
    long_rows = [r for r in rows if not r['key'].startswith('probe')]
    report['long_responses'] += len(long_rows)
    loaded[data['label']] = long_rows
    phases = defaultdict(list)
    rounds = defaultdict(list)
    for row in long_rows:
        phases[row['key'].split(':')[1] if ':' in row['key'] else 'default'].append(row)
        if ':' not in row['key']:
            rounds[row['key'].split('@')[1] if '@' in row['key'] else '1'].append(row)
    report['runs'][data['label']] = dict(
        phases={key: metrics(rr) for key, rr in phases.items()},
        rounds={key: metrics(rr) for key, rr in rounds.items()})

for baseline, candidate in [('mtp4-b', 'mtp8-p90-b'), ('mtp8-p90-b', 'mtp8-p90-profile')]:
    if baseline not in loaded or candidate not in loaded:
        continue
    comparison = dict(baseline=baseline, candidate=candidate, cases=[])
    for case in ('utilities', 'ttl_cache', 'algorithms', 'matrices'):
        rows = [[r for r in loaded[label] if r['key'].split('@')[0] == case]
                for label in (baseline, candidate)]
        assert all(len(rr) == 2 for rr in rows), (baseline, candidate, case)
        values = [metrics(rr) for rr in rows]
        comparison['cases'].append(dict(
            case=case, measurements=values,
            output_tokens=[[r['response']['timings']['predicted_n'] for r in rr] for rr in rows],
            speedup_percent=(values[1]['weighted_tps'] / values[0]['weighted_tps'] - 1) * 100,
            mean_request_seconds=[v['request_seconds'] / v['requests'] for v in values]))
    values = [metrics(loaded[label]) for label in (baseline, candidate)]
    comparison['overall'] = dict(measurements=values,
        speedup_percent=(values[1]['weighted_tps'] / values[0]['weighted_tps'] - 1) * 100,
        request_time_reduction_percent=(1 - values[1]['request_seconds'] / values[0]['request_seconds']) * 100)
    report['comparisons'].append(comparison)

assert loaded, 'no complete results found'
(root / 'summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(responses=report['responses'], long_responses=report['long_responses'],
                     comparisons=[dict(baseline=c['baseline'], candidate=c['candidate'], **c['overall'])
                                  for c in report['comparisons']]), indent=2))
