"""Hook the verified PC 0.39 recorder and video clock into the local Voice Host.

Only the original classes' public methods are wrapped. Recorder errors always
propagate, and a failed Voice call is logged separately without blocking video.
"""
from __future__ import annotations
import json
import os
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

STATE=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'VLab Voice' / 'host.json'
ERRORS=STATE.with_name('bridge-errors.log')

def _send(action,video='',origin_monotonic=None,end_monotonic=None,recording_id=None):
    data=json.loads(STATE.read_text(encoding='utf-8'))
    if data.get('url')!='http://127.0.0.1:8790':raise ValueError('Unexpected Voice Host address')
    body=dict(action=action,video=str(video))
    if recording_id is not None:body['recording_id']=str(recording_id)
    if origin_monotonic is not None:
        body['origin_monotonic']=float(origin_monotonic)
        body['auto_from_void_eye']=True
    if end_monotonic is not None:body['end_monotonic']=float(end_monotonic)
    request=urllib.request.Request(data['url']+'/api/control',json.dumps(body).encode(),
       headers={'Content-Type':'application/json','Authorization':'Bearer '+data['admin']})
    with urllib.request.urlopen(request,timeout=3) as response:return json.load(response)

def _log(action,exc):
    try:
        ERRORS.parent.mkdir(parents=True,exist_ok=True)
        with ERRORS.open('a',encoding='utf-8') as f:f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {action}: {type(exc).__name__}: {exc}\n')
    except OSError:pass

def patch_main(ns,send=_send):
    indexer=ns['LiveIndexer'];manager=ns['RecordingManager']
    original_start=manager.start;original_stop=manager.stop
    videos={};starts={}
    def retry(action,*args,**kwargs):
        for attempt in range(8):
            try:return send(action,*args,**kwargs)
            except Exception as exc:
                if attempt==7 or isinstance(exc,urllib.error.HTTPError) and exc.code in (400,401,403,404):
                    _log(action,exc);return
                time.sleep(min(2,.25*2**attempt))
    def start(self,sid):
        result=original_start(self,sid);videos[sid]=str(self.final_path);return result
    def make_indexer(catalog,sid,capture_clock,preparer):
        result=indexer(catalog,sid,capture_clock,preparer)
        video=videos.get(sid,'')
        worker=threading.Thread(target=retry,args=('start',video,capture_clock),
            kwargs={'recording_id':str(sid)},name='voice-session-start',daemon=False)
        starts[sid]=worker;worker.start();return result
    def stop(self,sid):
        end_clock=time.monotonic()
        try:return original_stop(self,sid)
        finally:
            starter=starts.pop(sid,None)
            if starter is not None:
                def finish():
                    starter.join()
                    retry('stop',end_monotonic=end_clock,recording_id=str(sid))
                # Give the bounded stop retries time to finish during normal desktop shutdown.
                threading.Thread(target=finish,name='voice-session-stop',daemon=False).start()
            videos.pop(sid,None)
    manager.start=start;manager.stop=stop;ns['LiveIndexer']=make_indexer
