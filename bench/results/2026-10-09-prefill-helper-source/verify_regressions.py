"""Validate the final prefix/session replay and compare coding output with the installed baseline."""
import gzip
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent


def read(name):
    p = OUT/name
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    with gzip.open(p.with_name(p.name+'.gz'), 'rt', encoding='utf-8') as f:
        return json.load(f)


sessions = read('sessions-final-result.json')
assert sessions['ok'] and len(sessions['requests']) == 17
assert all(r['valid'] for r in sessions['requests'])
returning = [r for r in sessions['requests'] if r['group'] in ('session-return','session-tool','session-rewind')]
assert len(returning) == 8 and all(r['timings']['cache_n'] > 0 for r in returning)
old_sessions = {r['key']:r for r in read('previous-sessions-result.json')['requests']}
session_same = all(r['text'] == old_sessions[r['key']]['text'] and r['usage'] == old_sessions[r['key']]['usage']
                   for r in sessions['requests'])
assert session_same

coding = read('coding-final-result.json')
assert coding['ok'] and len(coding['requests']) == 6
assert all(r['valid'] for r in coding['requests'])
old_coding = {r['key']:r for r in read('previous-coding-result.json')['requests']}
different = []
rows = []
for r in coding['requests']:
    response = r['response']
    text = response['choices'][0]['message']['content']
    old = old_coding[r['key']]['response']['choices'][0]['message']['content']
    if text != old:
        different.append(r['key'])
    rows.append(dict(key=r['key'], valid=r['valid'], seconds=r['seconds'], timings=response['timings'],
                     matches_previous=text==old, answer_sha256=hashlib.sha256(text.encode()).hexdigest()))
long = [r for r in rows if r['key'] in ('utilities','ttl_cache','algorithms','matrices')]
tokens = sum(r['timings']['predicted_n'] for r in long)
seconds = sum(r['timings']['predicted_ms'] for r in long)/1000
summary = dict(sessions=dict(requests=17, valid=17, returns=8, return_hits=8,
    return_wall_s=sum(r['wall_s'] for r in returning), wall_s=sum(r['wall_s'] for r in sessions['requests']),
    matches_previous=session_same), coding=dict(requests=6, valid=6, different_answers=different,
    long_tokens=tokens, long_decode_s=seconds, long_decode_tps=tokens/seconds,
    long_wall_s=sum(r['seconds'] for r in long), rows=rows))
(OUT/'regression-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
