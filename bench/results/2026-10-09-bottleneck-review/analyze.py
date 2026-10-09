"""Recompute the next-step review from archived results; never start a model."""
import gzip
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent/'2026-10-09-part2-prefill-0141'


def read(name):
    p = SOURCE/name
    if not p.exists():
        p = p.with_name(p.name+'.gz')
    data = p.read_bytes()
    return (gzip.decompress(data) if p.suffix == '.gz' else data).decode('utf-8')


def data(name):
    return json.loads(read(name))


def aggregate(rows, coding=False):
    timings = [r['response']['timings'] if coding else r['timings'] for r in rows]
    wall = sum(r['seconds'] if coding else r['wall_s'] for r in rows)
    prompt = sum(t['prompt_ms'] for t in timings)/1000
    decode = sum(t['predicted_ms'] for t in timings)/1000
    return dict(requests=len(rows), wall_s=wall, prompt_s=prompt, decode_s=decode,
                remaining_wall_s=wall-prompt-decode, prompt_percent=100*prompt/wall,
                decode_percent=100*decode/wall, reused_tokens=sum(t['cache_n'] for t in timings),
                draft_accept_percent=100*sum(t['draft_n_accepted'] for t in timings)/sum(t['draft_n'] for t in timings))


def cpu_observations(label):
    rows = data(label+'-result.json')['requests']
    samples = [json.loads(line) for line in read(label+'-memory.jsonl').splitlines() if line.strip()]
    observations = []
    for r in rows:
        if r['group'] != 'cold':
            continue
        ss = [s for s in samples if 'processes' in s and
              r['started_epoch'] <= s['epoch_s'] <= r['started_epoch']+r['wall_s']]
        if len(ss) < 2:
            continue
        def cpu(s):
            return {p['pid']:sum(p['cpu_seconds'][k] for k in ('user','system'))
                    for p in s['processes'] if p['name'].lower() == 'strata.exe'}
        first, last = ss[0], ss[-1]
        a, b = cpu(first), cpu(last)
        common = a.keys() & b.keys()
        if len(common) != 1:
            continue
        pid = next(iter(common))
        span = last['epoch_s']-first['epoch_s']
        observations.append(dict(key=r['key'], prompt_tokens=r['timings']['prompt_n'], samples=len(ss),
                                 sampled_span_s=span, average_logical_cpu_equivalents=(b[pid]-a[pid])/span))
    return observations


labels = ['v141-direct-a','v141-direct-b']
cold = [r for label in labels for r in data(label+'-result.json')['requests'] if r['group'] == 'cold']
coding = data('coding-final-result.json')['requests']
long_keys = ('utilities','ttl_cache','algorithms','matrices')
long_code = [r for r in coding if r['key'] in long_keys]
sessions = data('sessions-final-result.json')['requests']
returning = [r for r in sessions if r['group'] in ('session-return','session-tool','session-rewind')]
assert len(cold) == 20 and len(long_code) == 4 and len(returning) == 8
log = read('coding-final-engine.log')
helper_rows = re.findall(r'CUDA1: (\d+) expert entries, (\d+) active layer launches, ([\d.]+) MiB returned .*?host (\d+) ms staging\+launching, (\d+) ms waiting', log)
assert len(helper_rows) == len(coding)
helper = [row for row,r in zip(helper_rows,coding) if r['key'] in long_keys]
long_summary = aggregate(long_code, True)
wait_ms = sum(int(r[4]) for r in helper)
cpu = {label:cpu_observations(label) for label in ['baseline-b',*labels]}
cpu_ranges = {}
for label, rows in cpu.items():
    values = [r['average_logical_cpu_equivalents'] for r in rows if r['prompt_tokens'] >= 2000]
    cpu_ranges[label] = dict(min=min(values), max=max(values), median=statistics.median(values))
summary = dict(
    evidence='../2026-10-09-part2-prefill-0141',
    method='Offline recomputation only; CPU samples include compute, driver work and spinning; helper counters include prompt and decode.',
    cold=aggregate(cold), long_code=long_summary,
    edit=aggregate([r for r in coding if r['key'] == 'edit_utilities'],True),
    session_returns=aggregate(returning),
    long_code_helper=dict(layer_launches=sum(int(r[1]) for r in helper),
                          returned_mib=sum(float(r[2]) for r in helper),
                          host_ms=sum(int(r[3]) for r in helper), wait_ms=wait_ms,
                          wait_percent_of_complete_requests=wait_ms/(10*long_summary['wall_s'])),
    graph_capture_free_vram=[dict(window=int(t),free_before_mib=int(m))
                             for t,m in re.findall(r'capturing the (\d+)-token window \((\d+) MiB of VRAM free\)',log)],
    long_prompt_cpu_ranges=cpu_ranges, cpu_observations=cpu,
)
(ROOT/'analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k != 'cpu_observations'},ensure_ascii=False,indent=2))
