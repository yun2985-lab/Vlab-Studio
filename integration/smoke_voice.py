"""Windows installed Voice Host smoke: a recorder clock round-trip and local model load."""
import json,os,time,urllib.request
from pathlib import Path

state=Path(os.environ['VLAB_SMOKE_STATE'])
for _ in range(80):
    if state.is_file():break
    time.sleep(.5)
else:raise RuntimeError('Voice Host state file absent')
meta=json.loads(state.read_text(encoding='utf-8'))
assert meta['url']=='http://127.0.0.1:8790'
with urllib.request.urlopen(meta['url']+'/',timeout=2) as response:
    assert response.status==200 and '오브젝트 음성 알림' in response.read().decode('utf-8')
def post(body):
    r=urllib.request.Request(meta['url']+'/api/control',json.dumps(body).encode(),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+meta['admin']})
    with urllib.request.urlopen(r,timeout=12) as response:return json.load(response)
origin=time.monotonic()
started=post(dict(action='start',auto_from_void_eye=True,origin_monotonic=origin,video='smoke-video.mkv'))
assert started['state']=='recording' and started['model_ready']
time.sleep(.25)
stopped=post(dict(action='stop',end_monotonic=time.monotonic()))
assert stopped['state'] in ('recorded','transcribing','complete')
sid=started['session_id']
session=Path(os.environ['LOCALAPPDATA'])/'VLab Voice'/'recordings'/sid
def get(route):
    request=urllib.request.Request(meta['url']+route,headers={'Authorization':'Bearer '+meta['admin']})
    with urllib.request.urlopen(request,timeout=12) as response:return json.load(response)
for _ in range(120):
    data=next(s for s in get('/api/sessions')['sessions'] if s['session_id']==sid)
    if data['state'] in ('complete','stt_failed'):break
    time.sleep(.5)
assert data['state']=='complete',data
assert (session/'subtitles.json').exists()
get('/api/subtitles?session_id='+sid)
print('PASS: installed Voice Host UI, recorder clock, start/stop, packaged offline STT model initialization')
