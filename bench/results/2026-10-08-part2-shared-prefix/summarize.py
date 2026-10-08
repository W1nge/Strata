"""Recompute request, memory and cache measurements from retained raw evidence."""
import gzip
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parent


def read(name):
    path = ROOT / name
    return path.read_text(encoding='utf-8') if path.exists() else gzip.decompress(path.with_suffix(path.suffix+'.gz').read_bytes()).decode('utf-8')


def rows_summary(rows):
    return dict(count=len(rows), wall_s=sum(r['wall_s'] for r in rows),
        ttft_median_s=statistics.median(r['ttft_s'] for r in rows),
        wall_min_s=min(r['wall_s'] for r in rows), wall_max_s=max(r['wall_s'] for r in rows),
        cached=sum(r['timings']['cache_n'] for r in rows),
        read=sum(r['timings']['prompt_n'] for r in rows),
        hits=sum(r['timings']['cache_n'] > 0 for r in rows))


def summarize(label):
    data = json.loads(read(label+'-result.json'))
    if not data['ok']:
        raise AssertionError('Incomplete run: '+label)
    rows = data['requests']
    groups = dict(all=rows, prefix_repeat=[r for r in rows if r['key'] in ('prefix-1','prefix-2','prefix-3')],
                  session_return=[r for r in rows if r['group'] in ('session-return','session-tool','session-rewind')],
                  session_plain=[r for r in rows if r['group'] == 'session-return'],
                  session_tool_edit=[r for r in rows if r['group'] in ('session-tool','session-rewind')])
    out = {key: rows_summary(value) for key,value in groups.items()}
    samples = [json.loads(line) for line in read(label+'-memory.jsonl').splitlines()]
    # Match the measured request interval: after the warm response through the last response.
    active = [s for s in samples if 'memory' in s and 1 <= s['completed_requests'] < len(rows)]
    out['memory'] = dict(sample_count=len(active),
        available_min_gib=min(s['memory']['available'] for s in active)/2**30,
        available_median_gib=statistics.median(s['memory']['available'] for s in active)/2**30,
        c_drive_read_gib=(active[-1]['physical_disks']['PhysicalDrive2']['read_bytes']-
                          active[0]['physical_disks']['PhysicalDrive2']['read_bytes'])/2**30)
    log = read(label+'-engine.log')
    out['cache_log'] = dict(skips=len(re.findall(r'conversation cache: skip parking',log)),
        restores=len(re.findall(r'conversation cache: restored',log)),
        parked_bytes_max=max([int(s) for s in re.findall(r'parked=\d+ bytes=(\d+)',log)] or [0]),
        snapshot_bytes_max=max([int(s) for s in re.findall(r'snapshot_bytes=(\d+)',log)] or [0]))
    out['gpu'] = [data['gpu_before'], data['gpu_after']]
    return data, out


if __name__ == '__main__':
    results, raw = {}, {}
    for label in ('baseline-c','cache-a','fixed-a','fixed-b'):
        try:
            raw[label],results[label] = summarize(label)
        except FileNotFoundError:
            continue
    base = raw['baseline-c']['requests']
    for label, data in raw.items():
        rows = data['requests']
        assert [r['key'] for r in rows] == [r['key'] for r in base]
        assert [r['text'] for r in rows] == [r['text'] for r in base], label+' output differs'
        for original,current in zip(base,rows):
            request = dict(current['request'])
            request.pop('strata_prefix',None)
            assert original['request'] == request, label+' request differs'
            assert original['usage']['prompt_tokens'] == current['usage']['prompt_tokens']
            assert original['usage']['completion_tokens'] == current['usage']['completion_tokens']
        if label.startswith('fixed-'):
            assert results[label]['session_return']['hits'] == 8
            assert results[label]['cache_log']['skips'] == 0
            assert results[label]['memory']['available_min_gib'] >= 6
            assert results[label]['cache_log']['parked_bytes_max'] <= 1536*2**20
    results['parity'] = dict(identical_answers={label:len(data['requests']) for label,data in raw.items()},
                             requests_equal_except_prefix=True)
    (ROOT/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False,indent=2))
