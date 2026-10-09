"""Recompute the bounded cold-prompt comparison; also reads the compressed repository archive."""
import argparse
import gzip
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent


def read(path):
    if not path.exists():
        path = path.with_name(path.name+'.gz')
    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return f.read()
    return path.read_text(encoding='utf-8')


def summary(label):
    data = json.loads(read(ROOT/(label+'-result.json')))
    rows = [r for r in data['requests'] if r['group'] == 'cold']
    groups = {}
    for row in rows:
        groups.setdefault(row['key'].rsplit('-r', 1)[0], []).append(row)
    per_case = {}
    for key, rr in groups.items():
        per_case[key] = dict(n=len(rr), prompt_n=[r['timings']['prompt_n'] for r in rr],
            prompt_s=[r['timings']['prompt_ms']/1000 for r in rr],
            prompt_median_s=statistics.median(r['timings']['prompt_ms']/1000 for r in rr),
            ttft_median_s=statistics.median(r['ttft_s'] for r in rr),
            wall_median_s=statistics.median(r['wall_s'] for r in rr))
    samples = [json.loads(line) for line in read(ROOT/(label+'-memory.jsonl')).splitlines() if line.strip()]
    samples = [s for s in samples if 'memory' in s and rows and
               rows[0]['started_epoch'] <= s['epoch_s'] <= rows[-1]['started_epoch']+rows[-1]['wall_s']]
    memory = {}
    if samples:
        memory = dict(sample_count=len(samples), available_min_gib=min(s['memory']['available'] for s in samples)/2**30,
            available_median_gib=statistics.median(s['memory']['available'] for s in samples)/2**30,
            physical_disk_reads_gib={k:(samples[-1]['physical_disks'][k]['read_bytes']-v['read_bytes'])/2**30
                                     for k,v in samples[0]['physical_disks'].items()})
    out = dict(ok=data['ok'], requests=len(data['requests']), expected_requests=data['expected_requests'],
        startup_s=data['requests'][0]['started_epoch']-data['started_epoch'] if data['requests'] else None,
        cold_requests=len(rows), all_valid=all(r['valid'] for r in data['requests']),
        all_cold_cache_misses=all(r['timings']['cache_n']==0 for r in rows),
        request_wall_s=sum(r['wall_s'] for r in data['requests']), cold_wall_s=sum(r['wall_s'] for r in rows),
        cold_prompt_s=sum(r['timings']['prompt_ms'] for r in rows)/1000,
        exe_sha256=data['exe_sha256'], config_sha256=data['config_sha256'],
        fixture_sha256=data['fixture_sha256'], per_case=per_case, memory=memory)
    if 'error' in data:
        out['error'] = data['error']
    return out, data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('labels', nargs='+')
    parser.add_argument('--save', type=Path)
    args = parser.parse_args()
    out, raw = {}, {}
    for label in args.labels:
        out[label], raw[label] = summary(label)
    baseline = raw[args.labels[0]]
    base = {r['key']:r for r in baseline['requests']}
    comparison = {}
    for label in args.labels[1:]:
        common = [r for r in raw[label]['requests'] if r['key'] in base]
        comparison[label] = dict(common_requests=len(common),
            requests_identical=all(r['request']==base[r['key']]['request'] for r in common),
            answers_identical=all(r['text']==base[r['key']]['text'] for r in common),
            token_counts_identical=all(r['usage']==base[r['key']]['usage'] for r in common),
            different_answers=[r['key'] for r in common if r['text']!=base[r['key']]['text']],
            cold_prompt_reduction_percent=100*(1-out[label]['cold_prompt_s']/out[args.labels[0]]['cold_prompt_s']))
    result = dict(runs=out, comparison=comparison)
    if args.save:
        args.save.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
