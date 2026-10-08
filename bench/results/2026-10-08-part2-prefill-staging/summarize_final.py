"""Recompute request-weighted timings and exact response comparisons from saved evidence."""
import gzip
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent
CORE = {'utilities', 'ttl_cache', 'algorithms', 'matrices'}

def base_key(key):
    return key.split('@')[0].split(':')[0]

def aggregate(requests):
    timings = [r['response']['timings'] for r in requests]
    tokens = sum(t['predicted_n'] for t in timings)
    decode_ms = sum(t['predicted_ms'] for t in timings)
    return dict(requests=len(requests), output_tokens=tokens, decode_ms=decode_ms,
                weighted_tps=1000*tokens/decode_ms if decode_ms else None,
                request_seconds=sum(r['seconds'] for r in requests),
                prompt_seconds=sum(t['prompt_ms'] for t in timings)/1000)

runs, data = {}, {}
for path in sorted(ROOT.glob('*-result.json')):
    result = json.loads(path.read_text(encoding='utf-8'))
    label = result['label']
    data[label] = result
    req = result['requests']
    row = dict(ok=result['ok'], expected=result.get('expected_requests'), error=result.get('error'),
               valid_responses=sum(bool(r.get('valid')) for r in req),
               all_finish_reasons_stop=all(r['response']['choices'][0]['finish_reason']=='stop' for r in req),
               all=aggregate(req),
               core_coding=aggregate([r for r in req if base_key(r['key']) in CORE]),
               large_prompts=aggregate([r for r in req if base_key(r['key']) in {'long', 'long5k'}]),
               edits=[dict(key=r['key'], seconds=r['seconds'], **r['response']['timings'])
                      for r in req if base_key(r['key'])=='edit_utilities'])
    mem = ROOT / (label + '-memory.jsonl')
    opener = open
    if not mem.exists():
        mem = mem.with_suffix('.jsonl.gz')
        opener = gzip.open
    if mem.exists():
        with opener(mem, 'rt', encoding='utf-8') as stream:
            samples = [json.loads(line) for line in stream]
        # Same historical bounds for every arm: last saved completed-request count, sampled once a second.
        samples = [s for s in samples if 'memory' in s and 3 <= s.get('completed_requests', -1) < len(req)]
        if samples:
            available = [s['memory']['available']/2**30 for s in samples]
            row['memory_after_three_requests'] = dict(samples=len(samples), available_gib_min=min(available),
                available_gib_median=statistics.median(available),
                physical_read_gib={name:(values['read_bytes']-samples[0]['physical_disks'][name]['read_bytes'])/2**30
                                   for name, values in samples[-1]['physical_disks'].items()})
    runs[label] = row

pairs = [('release-control-a','release-candidate-a'), ('release-control-a','release-candidate-b'),
         ('coding-control-a','coding-candidate-a'), ('coding-candidate-a','01404-coding-a'),
         ('release-candidate-a','01404-general-a')]
comparisons = []
for left, right in pairs:
    if left not in data or right not in data:
        continue
    a = {r['key']:r['response'] for r in data[left]['requests']}
    b = {r['key']:r['response'] for r in data[right]['requests']}
    keys = sorted(a.keys() & b.keys())
    comparisons.append(dict(left=left, right=right, keys_match=a.keys()==b.keys(), compared=len(keys),
        text_identical=sum(a[k]['choices'][0]['message']['content']==b[k]['choices'][0]['message']['content'] for k in keys),
        prompt_tokens_identical=sum(a[k]['timings']['prompt_n']==b[k]['timings']['prompt_n'] for k in keys),
        output_tokens_identical=sum(a[k]['timings']['predicted_n']==b[k]['timings']['predicted_n'] for k in keys)))

reference_comparisons = []
if '01404-short448-a' in data:
    relative = Path('bench/results/2026-10-08-part2-mapped-output/mapped-output-b-result.json')
    reference = ROOT.parent / '2026-10-08-part2-mapped-output' / relative.name
    if not reference.exists():
        reference = Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr') / relative
    old = json.loads(reference.read_text(encoding='utf-8'))
    answers = {r['key']:r['response'] for r in old['requests']}
    req = data['01404-short448-a']['requests']
    reference_comparisons.append(dict(reference=str(relative), reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        candidate='01404-short448-a', compared=len(req),
        text_identical=sum(answers[r['key']]['choices'][0]['message']['content']==r['response']['choices'][0]['message']['content'] for r in req),
        note='Earlier process had other code requests between these cases; this comparison checks text, not timing.'))

summary = dict(runs=runs, comparisons=comparisons, reference_comparisons=reference_comparisons, starts=len(runs),
               responses=sum(r['all']['requests'] for r in runs.values()),
               valid_responses=sum(r['valid_responses'] for r in runs.values()),
               successful_starts=sum(r['ok'] for r in runs.values()),
               known_failed_diagnostic='trace-a: additional timing stalled at the 5K prompt; not a normal-performance arm')
(ROOT / 'final-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
for label, row in runs.items():
    print(json.dumps(dict(label=label, ok=row['ok'], requests=row['all']['requests'],
        total_seconds=row['all']['request_seconds'], long_prompt_seconds=row['large_prompts']['prompt_seconds'],
        coding=row['core_coding'], edits=row['edits'], memory=row.get('memory_after_three_requests')), ensure_ascii=False))
print(json.dumps(dict(comparisons=comparisons, starts=summary['starts'], responses=summary['responses'],
                     successful_starts=summary['successful_starts']), ensure_ascii=False))
