import json,pathlib,sys,threading,time,urllib.request,runpy,_thread,re
label=sys.argv[1];gpus=[int(x) for x in sys.argv[2].split(',')];split=sys.argv[3] if len(sys.argv)>3 else 'auto'
root=pathlib.Path('C:/Users/Winge/Documents/Playground/Strata-optimization-pr');out=pathlib.Path('E:/strata-setup/part2-dual')
c=json.loads(pathlib.Path('C:/strata-models/strata-256k-int8.json').read_text(encoding='utf-8'));a=c['args'];new=[];i=0
while i<len(a):
 if a[i] in ('--cache-idle-seconds','--cache-expire-seconds','--cache-disk-dir'):i+=2;continue
 new.append(a[i]);i+=1
a=new;a[a.index('--max-context')+1]='4096';a[a.index('--prefill')+1]='128';c['args']=a
if 'large' in label:
 a[a.index('--max-context')+1]='8192';a[a.index('--prefill')+1]='auto:2048'
c.update(exe=str(out/'build/strata.exe'),cwd=str(out/'build'),log=str(out/(label+'-engine.log')),gpu=gpus)
if len(sys.argv)>4:c['env']['STRATA_SPLIT_COVER_B']=sys.argv[4]
if split=='helper':
 j=c['args'].index('--resident-budget-gib');del c['args'][j:j+2]
 c['args']+=['--mmap-experts','--expert-cache-device1','auto','--remote-expert-opt']
 c.pop('gpu',None)
 c['args']+=['--gpu',','.join(map(str,gpus))]
 if label.startswith('resident'):
  c['args']+=['--resident-experts']
  c['env']['STRATA_RESIDENT_HEADROOM_GIB']='6'
elif len(gpus)>1:c['layer_split']=split
config=out/(label+'-config.json');config.write_text(json.dumps(c,indent=2),encoding='utf-8')
sys.path.insert(0,str(root/'serve'));sys.path.insert(0,str(root/'tools'))
def request(path,data=None):
 req=urllib.request.Request('http://127.0.0.1:18997'+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=300) as r:return json.load(r)
def test():
 result={'label':label,'gpu':gpus}
 try:
  deadline=time.time()+300
  while True:
   try:result['health']=request('/health');break
   except Exception:
    if time.time()>deadline:raise
    time.sleep(1)
  req={'model':'qwen3.8-flash-next','messages':[{'role':'user','content':'Answer with the number only: what is 2 plus 2?'}],'max_tokens':16,'chat_template_kwargs':{'enable_thinking':False},'temperature':0,'stream':False}
  for key in ('first','repeat'):
   result[key]=request('/v1/chat/completions',req);assert result[key]['choices'][0]['message']['content'].strip()=='4'
  req['messages']=[{'role':'user','content':('The secret word is apple. '*(200 if 'large' in label else 40))+'Repeat the secret word 30 times separated by spaces, without any introduction.'}];req['max_tokens']=96
  if 'steady' in label:
   req['messages']=[{'role':'user','content':('The secret word is apple. '*200)+'Count from 1 to 100 in order. Output only the numbers separated by commas.'}];req['max_tokens']=512
  result['workload']=request('/v1/chat/completions',req)
  answer=result['workload']['choices'][0]['message']['content']
  if 'steady' in label:assert [int(x) for x in re.findall(r'\d+',answer)]==list(range(1,101)),answer
  else:assert answer.lower().count('apple')>=20,answer
  result['status']=request('/v1/status');result['ok']=True
 except Exception as e:result['ok']=False;result['error']=repr(e)
 finally:
  (out/(label+'-http.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');_thread.interrupt_main()
threading.Thread(target=test,daemon=True).start()
sys.argv=['serve/server.py','--engine','strata','--config',str(config),'--host','127.0.0.1','--port','18997']
runpy.run_path(str(root/'serve/server.py'),run_name='__main__')
