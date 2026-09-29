"""Self-hosted WebRTC prototype. Live downlink is mixed, recordings never are."""
import argparse, asyncio, contextlib, json, secrets, ssl, time, uuid
from collections import deque
from fractions import Fraction
from pathlib import Path
import numpy as np
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, AudioStreamTrack
from aiortc.mediastreams import MediaStreamError
from av import AudioFrame, AudioResampler
from .core import Session
from .recovery import restore, RecordingLock
from .objectives import ObjectiveService, PROFILE

class MixTrack(AudioStreamTrack):
    def __init__(self):
        super().__init__(); self.queues = {}; self.pts = 0; self.started = None
    def push(self, uid, samples):
        self.queues.setdefault(uid, deque(maxlen=5)).append(samples)
    async def recv(self):
        if self.started is None: self.started = time.monotonic()
        await asyncio.sleep(max(0, self.started+self.pts/48000-time.monotonic()))
        mixed = np.zeros(960, dtype=np.int32)
        for q in self.queues.values():
            if q: mixed += q.popleft().astype(np.int32)
        frame = AudioFrame.from_ndarray(np.clip(mixed,-32768,32767).astype(np.int16)[None,:],
                                        format='s16', layout='mono')
        frame.sample_rate=48000; frame.pts=self.pts; frame.time_base=Fraction(1,48000)
        self.pts += 960
        return frame

class Host:
    def __init__(self, root, capacity=5, model_path=None, state_file=None):
        if not 1 <= capacity <= 10: raise ValueError('인원 제한은 1~10명입니다.')
        self.capacity=capacity; self.root=root; self.model_path=model_path; self.state_file=Path(state_file) if state_file else None
        self.code=secrets.token_hex(6).upper(); self.admin=secrets.token_urlsafe(32)
        self.peers={}; self.session=None; self.stt_task=None; self.lock=asyncio.Lock()
        self.attempts={}; self.events=set(); self.objectives=ObjectiveService()
        self.recording_lock=RecordingLock(root)
        self.sessions={};self.captures={};self.pending=deque();self.queued=set();self.transcribing_id=None;self.finalizers={};self.recovery_errors=[]
        for path in sorted(Path(root).glob('*/session.json'),key=lambda p:p.stat().st_mtime):
            try:
                session=restore(path.parent);self.sessions[session.id]=session;self.session=session
            except Exception as e:self.recovery_errors.append(dict(session_id=path.parent.name,error=str(e)))

    def status(self):
        return dict(objectives=self.objectives.clock.status(), capacity=self.capacity, members=[dict(user_id=k,name=p['name'],host=p['host'],
            connection=p['pc'].connectionState, level=round(p.get('level',0),3) if time.monotonic()-p.get('level_at',0)<1 else 0)
            for k,p in self.peers.items()], state=self.session.data['state'] if self.session else 'idle',
            session_id=self.session.id if self.session else None,
            error=self.session.data.get('error') if self.session else None,
            elapsed=round(time.monotonic()-self.session.origin,1) if self.session and self.session.data['state']=='recording' else (self.session.data.get('duration',self.session.data.get('end_monotonic',self.session.origin)-self.session.origin) if self.session else 0),
            recorded_tracks=len(self.session.tracks) if self.session else 0,
            model_ready=bool(self.model_path and Path(self.model_path).is_dir()),
            pending_transcriptions=len(self.pending),transcribing_session=self.transcribing_id,
            recovery_errors=len(self.recovery_errors))

    async def broadcast(self):
        for ws in list(self.events):
            try: await ws.send_json(self.status())
            except Exception: self.events.discard(ws)

    async def ingest(self, uid, track):
        resampler=AudioResampler(format='s16',layout='mono',rate=48000,frame_size=960)
        anchor=None; first_pts=None; count=0
        try:
            while True:
                frame=await track.recv()
                for f in resampler.resample(frame):
                    if anchor is None:
                        anchor=time.monotonic()-f.samples/48000
                        first_pts=f.pts
                    stamp=anchor+((f.pts-first_pts)/48000 if f.pts is not None and first_pts is not None else count/48000)
                    count += f.samples
                    samples=f.to_ndarray().reshape(-1).copy()
                    if uid in self.peers:
                        self.peers[uid]['level']=min(1.0,float(np.sqrt(np.mean(samples.astype(np.float64)**2)))/12000)
                        self.peers[uid]['level_at']=time.monotonic()
                    for other,p in self.peers.items():
                        if other != uid: p['mix'].push(uid,samples)
                    for session in list(self.captures.values()):
                        if session.data['state'] not in ('recording','finalizing'):continue
                        try:session.write(uid,self.peers.get(uid,{}).get('name','참가자'),samples.tobytes(),stamp)
                        except Exception as e:
                            session.stop();session.data['state']='recording_failed'
                            session.data['error']=str(e);session.save();await self.broadcast()
        except (MediaStreamError, asyncio.CancelledError): pass

    async def remove(self, uid):
        p=self.peers.pop(uid,None)
        if p:
            for task in p['tasks']:
                if task is not asyncio.current_task(): task.cancel()
            p['mix'].stop()
            await p['pc'].close()
            for other in self.peers.values(): other['mix'].queues.pop(uid,None)
            await self.broadcast()

    def admin_check(self, request):
        if not secrets.compare_digest(request.headers.get('Authorization',''), 'Bearer '+self.admin):
            raise web.HTTPUnauthorized()

    async def offer(self, request):
        body=await request.json()
        now=time.monotonic(); ip=request.remote
        recent=[x for x in self.attempts.get(ip,[]) if now-x<60]
        if len(recent)>=20: raise web.HTTPTooManyRequests()
        self.attempts[ip]=recent+[now]
        if not secrets.compare_digest(str(body.get('code','')),self.code): raise web.HTTPForbidden(text='방 코드가 다릅니다.')
        if body.get('consent') is not True: raise web.HTTPForbidden(text='녹음·전사 안내 확인이 필요합니다.')
        is_host=secrets.compare_digest(request.headers.get('Authorization',''), 'Bearer '+self.admin)
        async with self.lock:
            if len(self.peers)>=self.capacity: raise web.HTTPConflict(text='방이 가득 찼습니다.')
            if is_host and any(p['host'] for p in self.peers.values()): raise web.HTTPConflict(text='방장은 이미 입장했습니다.')
            if not is_host and not any(p['host'] for p in self.peers.values()): raise web.HTTPConflict(text='방장이 먼저 입장해야 합니다.')
            uid=uuid.uuid4().hex; pc=RTCPeerConnection(RTCConfiguration(iceServers=[])); mix=MixTrack()
            self.peers[uid]=dict(pc=pc,mix=mix,name=str(body.get('name','참가자'))[:40],host=is_host,tasks=[],token=secrets.token_urlsafe(24))
        @pc.on('track')
        def on_track(track):
            if track.kind=='audio': self.peers[uid]['tasks'].append(asyncio.create_task(self.ingest(uid,track)))
        @pc.on('connectionstatechange')
        async def state():
            if pc.connectionState in ('failed','closed'): await self.remove(uid)
        try:
            await pc.setRemoteDescription(RTCSessionDescription(sdp=body['sdp'],type='offer'))
            if len(pc.getTransceivers()) != 1 or pc.getTransceivers()[0].kind != 'audio':
                raise ValueError('참가자당 오디오 트랙 하나만 허용합니다.')
            pc.addTrack(mix)
            await pc.setLocalDescription(await pc.createAnswer())
            async def timeout():
                await asyncio.sleep(20)
                if pc.connectionState != 'connected': await self.remove(uid)
            self.peers[uid]['tasks'].append(asyncio.create_task(timeout()))
            await self.broadcast()
            return web.json_response(dict(sdp=pc.localDescription.sdp,type='answer',user_id=uid,token=self.peers[uid]['token']))
        except Exception as e:
            await self.remove(uid); raise web.HTTPBadRequest(text=str(e))

    def member(self, request):
        uid=request.query.get('user_id'); p=self.peers.get(uid)
        if not p or not secrets.compare_digest(request.headers.get('Authorization',''),'Bearer '+p['token']):
            raise web.HTTPUnauthorized()
        return uid

    async def leave(self,request):
        await self.remove(self.member(request)); return web.json_response({'ok':True})

    async def status_route(self,request):
        self.member(request); return web.json_response(self.status())

    def enqueue(self, session):
        if not self.model_path or session.id in self.queued or session.id==self.transcribing_id:return
        if session.data['state'] not in ('recorded','stt_failed'):return
        self.queued.add(session.id);self.pending.append(session)
        if self.stt_task is None or self.stt_task.done():self.stt_task=asyncio.create_task(self.process_queue())

    async def process_queue(self):
        while self.pending:
            session=self.pending.popleft();self.queued.discard(session.id)
            self.transcribing_id=session.id
            try:await asyncio.to_thread(session.transcribe,self.model_path)
            except Exception:pass  # Session persists the failure; subsequent jobs still run.
            finally:self.transcribing_id=None
            await self.broadcast()

    async def restore_jobs(self, app):
        for session in self.sessions.values():
            if session.data['state']=='recorded':self.enqueue(session)

    async def finalize(self, session):
        await asyncio.sleep(2)
        if session.data['state']=='finalizing':session.stop()
        self.captures.pop(session.id,None);self.enqueue(session)
        await self.broadcast()

    async def control(self,request):
        self.admin_check(request);body=await request.json();action=body.get('action')
        rid=body.get('recording_id')
        if rid is not None and (not isinstance(rid,str) or not rid or len(rid)>200):raise web.HTTPBadRequest(text='잘못된 경기 ID입니다.')
        selected=self.sessions.get(str(body.get('session_id','')))
        if rid is not None:selected=next((s for s in self.sessions.values() if s.data.get('recording_id')==rid),None)
        if action=='start':
            if selected is not None:
                if selected.data['video']!=str(body.get('video','')):raise web.HTTPConflict(text='경기 ID가 다른 영상에 사용되었습니다.')
                return web.json_response(self.status())
            if any(s.data['state']=='recording' for s in self.sessions.values()):raise web.HTTPConflict(text='이미 녹음 중입니다.')
            if not any(p['host'] for p in self.peers.values()) and not (body.get('auto_from_void_eye') is True and body.get('origin_monotonic') is not None):raise web.HTTPConflict(text='방장 음성 입장이 필요합니다.')
            try:session=Session(self.root,str(body.get('video','')),body.get('origin_monotonic'))
            except (ValueError,TypeError) as e:raise web.HTTPBadRequest(text=str(e))
            if rid is not None:session.data['recording_id']=rid;session.save()
            self.session=session;self.sessions[session.id]=session;self.captures[session.id]=session
        elif action=='stop':
            session=selected if rid is not None or body.get('session_id') else self.session
            if session is None:raise web.HTTPConflict(text='해당 녹음이 없습니다.')
            if session.id in self.finalizers:
                await asyncio.shield(self.finalizers[session.id])
            elif session.data['state']=='recording':
                end=body.get('end_monotonic')
                if end is not None:
                    try:
                        end=float(end)
                        if not __import__('math').isfinite(end) or end>time.monotonic()+1 or end<session.origin:raise ValueError()
                    except (ValueError,TypeError):raise web.HTTPBadRequest(text='잘못된 녹화 종료 시각입니다.')
                session.begin_finalize(end)
                task=asyncio.create_task(self.finalize(session));self.finalizers[session.id]=task
                await asyncio.shield(task)
            elif rid is None:raise web.HTTPConflict(text='녹음 중이 아닙니다.')
        elif action=='transcribe':
            session=selected or self.session
            if not self.model_path:raise web.HTTPConflict(text='로컬 모델 경로를 지정하세요.')
            if session is None or session.data['state'] not in ('recorded','stt_failed'):raise web.HTTPConflict(text='전사 가능한 녹음이 없습니다.')
            self.enqueue(session)
        else:raise web.HTTPBadRequest()
        await self.broadcast();return web.json_response(self.status())

    async def sessions_route(self,request):
        self.admin_check(request)
        return web.json_response(dict(sessions=[dict(session_id=s.id,video=s.data['video'],state=s.data['state'],
            recovery_notice=s.data.get('recovery_notice'),error=s.data.get('error')) for s in reversed(list(self.sessions.values()))],
            recovery_errors=self.recovery_errors))

    async def objective_control(self,request):
        self.admin_check(request)
        try:
            body=await request.json()
            if not isinstance(body,dict): raise ValueError('잘못된 요청입니다.')
            if 'enabled' in body:
                if body.get('profile')!=PROFILE:
                    raise ValueError('소환사의 협곡 일반/랭크 프로필을 확인하세요.')
                self.objectives.clock.enable(body['enabled'])
            elif 'kind' in body:
                self.objectives.clock.schedule_visible(body['kind'],body.get('spawn_at'))
            else: raise ValueError('알림 설정 또는 출현 시각이 필요합니다.')
        except (ValueError,TypeError) as e: raise web.HTTPBadRequest(text=str(e))
        return web.json_response(self.objectives.clock.status())

    async def subtitles(self,request):
        self.admin_check(request)
        session=self.sessions.get(request.query.get('session_id')) if request.query.get('session_id') else self.session
        if not session:raise web.HTTPNotFound()
        path=session.directory/'subtitles.json'
        if not path.exists(): raise web.HTTPNotFound(text='전사 결과가 아직 없습니다.')
        return web.FileResponse(path)

    async def publish_state(self,app):
        if not self.state_file: return
        self.state_file.parent.mkdir(parents=True,exist_ok=True)
        data=dict(code=self.code,admin=self.admin,pid=__import__('os').getpid(),url='http://127.0.0.1:8790')
        tmp=self.state_file.with_suffix('.tmp')
        tmp.write_text(json.dumps(data),encoding='utf-8')
        __import__('os').replace(tmp,self.state_file)

    async def clear_state(self,app):
        if not self.state_file: return
        try:
            data=json.loads(self.state_file.read_text(encoding='utf-8'))
            if data.get('admin')==self.admin: self.state_file.unlink(missing_ok=True)
        except (OSError,ValueError): pass

    async def close(self,app):
        for uid in list(self.peers): await self.remove(uid)
        if self.finalizers:await asyncio.gather(*self.finalizers.values(),return_exceptions=True)
        for session in self.sessions.values():
            if session.data['state']=='recording':session.stop()
        if self.stt_task:await self.stt_task

    async def release_recordings(self,app):
        self.recording_lock.close()

    def app(self):
        app=web.Application(client_max_size=128*1024)
        app.router.add_post('/api/offer',self.offer)
        app.router.add_get('/api/status',self.status_route)
        app.router.add_post('/api/leave',self.leave)
        app.router.add_post('/api/control',self.control)
        app.router.add_post('/api/objectives',self.objective_control)
        app.router.add_get('/api/subtitles',self.subtitles)
        app.router.add_get('/api/sessions',self.sessions_route)
        async def index(r): return web.FileResponse(Path(__file__).parent/'web'/'index.html')
        app.router.add_get('/',index)
        app.router.add_static('/assets/',Path(__file__).parent/'web',show_index=False)
        app.on_startup.append(self.objectives.start)
        app.on_startup.append(self.publish_state)
        app.on_startup.append(self.restore_jobs)
        app.on_shutdown.append(self.clear_state)
        app.on_shutdown.append(self.objectives.close)
        app.on_shutdown.append(self.close)
        app.on_cleanup.append(self.release_recordings)
        return app

def main():
    p=argparse.ArgumentParser(); p.add_argument('--bind',default='127.0.0.1'); p.add_argument('--port',type=int,default=8790)
    p.add_argument('--capacity',type=int,default=5); p.add_argument('--recordings',default='voice-recordings')
    p.add_argument('--model'); p.add_argument('--state-file'); p.add_argument('--cert'); p.add_argument('--key'); a=p.parse_args()
    if a.bind not in ('127.0.0.1','localhost') and not (a.cert and a.key): p.error('외부 접속에는 신뢰할 수 있는 HTTPS 인증서 --cert / --key가 필요합니다.')
    context=None
    if a.cert:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(a.cert,a.key)
    host=Host(a.recordings,a.capacity,a.model,a.state_file)
    print('방 코드:',host.code,'\n방장 전용 키 (공유 금지):',host.admin,flush=True)
    web.run_app(host.app(),host=a.bind,port=a.port,ssl_context=context)

if __name__=='__main__': main()
