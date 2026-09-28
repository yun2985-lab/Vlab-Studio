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
from pathlib import Path

STATE=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'VLab Voice' / 'host.json'
ERRORS=STATE.with_name('bridge-errors.log')

def _send(action,video='',origin_monotonic=None,end_monotonic=None):
    data=json.loads(STATE.read_text(encoding='utf-8'))
    if data.get('url')!='http://127.0.0.1:8790':raise ValueError('Unexpected Voice Host address')
    body=dict(action=action,video=str(video))
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
    videos={};active=set()
    def start(self,sid):
        result=original_start(self,sid)
        videos[sid]=str(self.final_path)
        return result
    def make_indexer(catalog,sid,capture_clock,preparer):
        # This is called immediately after a successful recorder.start() and
        # receives the same monotonic video clock as VOID EYE's live indexer.
        result=indexer(catalog,sid,capture_clock,preparer)
        try:
            send('start',videos.get(sid,''),capture_clock)
            active.add(sid)
        except Exception as exc:_log('start',exc)
        return result
    def stop(self,sid):
        end_clock=time.monotonic()
        try:return original_stop(self,sid)
        finally:
            if sid in active:
                active.remove(sid)
                def finish():
                    try:send('stop',end_monotonic=end_clock)
                    except Exception as exc:_log('stop',exc)
                threading.Thread(target=finish,name='voice-session-stop',daemon=True).start()
            videos.pop(sid,None)
    manager.start=start;manager.stop=stop;ns['LiveIndexer']=make_indexer
