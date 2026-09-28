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
    def __init__(self, root, capacity=5, model_path=None):
        if not 1 <= capacity <= 10: raise ValueError('인원 제한은 1~10명입니다.')
        self.capacity=capacity; self.root=root; self.model_path=model_path
        self.code=secrets.token_hex(6).upper(); self.admin=secrets.token_urlsafe(32)
        self.peers={}; self.session=None; self.stt_task=None; self.lock=asyncio.Lock()
        self.attempts={}; self.events=set(); self.objectives=ObjectiveService()

    def status(self):
        return dict(objectives=self.objectives.clock.status(), capacity=self.capacity, members=[dict(user_id=k,name=p['name'],host=p['host'],
            connection=p['pc'].connectionState, level=round(p.get('level',0),3) if time.monotonic()-p.get('level_at',0)<1 else 0)
            for k,p in self.peers.items()], state=self.session.data['state'] if self.session else 'idle',
            session_id=self.session.id if self.session else None,
            error=self.session.data.get('error') if self.session else None,
            elapsed=round(time.monotonic()-self.session.origin,1) if self.session and self.session.data['state']=='recording' else (self.session.data.get('duration',self.session.data.get('end_monotonic',self.session.origin)-self.session.origin) if self.session else 0),
            recorded_tracks=len(self.session.tracks) if self.session else 0,
            model_ready=bool(self.model_path and Path(self.model_path).is_dir()))

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
                    if self.session and self.session.data['state'] in ('recording','finalizing'):
                        try: self.session.write(uid,self.peers[uid]['name'],samples.tobytes(),stamp)
                        except Exception as e:
                            self.session.stop(); self.session.data['state']='recording_failed'
                            self.session.data['error']=str(e); self.session.save(); await self.broadcast()
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

    async def control(self,request):
        self.admin_check(request); body=await request.json(); action=body.get('action')
        if action=='start':
            if self.stt_task and not self.stt_task.done(): raise web.HTTPConflict(text='전사 완료 후 녹음하세요.')
            if self.session and self.session.data['state'] in ('recording','finalizing'): raise web.HTTPConflict(text='이미 녹음 중입니다.')
            if not any(p['host'] for p in self.peers.values()): raise web.HTTPConflict(text='방장 음성 입장이 필요합니다.')
            try: self.session=Session(self.root,str(body.get('video','')),body.get('origin_monotonic'))
            except (ValueError, TypeError) as e: raise web.HTTPBadRequest(text=str(e))
        elif action=='stop':
            if not self.session or self.session.data['state']!='recording': raise web.HTTPConflict(text='녹음 중이 아닙니다.')
            self.session.begin_finalize()
            await self.broadcast()
            # Drain in-flight RTP before sealing files; core trims at the original stop clock.
            await asyncio.sleep(2)
            self.session.stop()
            if self.model_path: self.stt_task=asyncio.create_task(self.transcribe())
        elif action=='transcribe':
            if not self.model_path: raise web.HTTPConflict(text='로컬 모델 경로를 지정하세요.')
            if not self.session or self.session.data['state'] not in ('recorded','stt_failed'): raise web.HTTPConflict(text='전사 가능한 녹음이 없습니다.')
            if self.stt_task and not self.stt_task.done(): raise web.HTTPConflict()
            self.stt_task=asyncio.create_task(self.transcribe())
        else: raise web.HTTPBadRequest()
        await self.broadcast(); return web.json_response(self.status())

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

    async def transcribe(self):
        try: await asyncio.to_thread(self.session.transcribe,self.model_path)
        except Exception: pass  # persisted error shown by status polling
        await self.broadcast()

    async def subtitles(self,request):
        self.admin_check(request)
        if not self.session: raise web.HTTPNotFound()
        path=self.session.directory/'subtitles.json'
        if not path.exists(): raise web.HTTPNotFound(text='전사 결과가 아직 없습니다.')
        return web.FileResponse(path)

    async def close(self,app):
        for uid in list(self.peers): await self.remove(uid)
        if self.session and self.session.data['state'] in ('recording','finalizing'): self.session.stop()
        if self.stt_task: await self.stt_task

    def app(self):
        app=web.Application(client_max_size=128*1024)
        app.router.add_post('/api/offer',self.offer)
        app.router.add_get('/api/status',self.status_route)
        app.router.add_post('/api/leave',self.leave)
        app.router.add_post('/api/control',self.control)
        app.router.add_post('/api/objectives',self.objective_control)
        app.router.add_get('/api/subtitles',self.subtitles)
        async def index(r): return web.FileResponse(Path(__file__).parent/'web'/'index.html')
        app.router.add_get('/',index)
        app.router.add_static('/assets/',Path(__file__).parent/'web',show_index=False)
        app.on_startup.append(self.objectives.start)
        app.on_shutdown.append(self.objectives.close)
        app.on_shutdown.append(self.close)
        return app

def main():
    p=argparse.ArgumentParser(); p.add_argument('--bind',default='127.0.0.1'); p.add_argument('--port',type=int,default=8790)
    p.add_argument('--capacity',type=int,default=5); p.add_argument('--recordings',default='voice-recordings')
    p.add_argument('--model'); p.add_argument('--cert'); p.add_argument('--key'); a=p.parse_args()
    if a.bind not in ('127.0.0.1','localhost') and not (a.cert and a.key): p.error('외부 접속에는 신뢰할 수 있는 HTTPS 인증서 --cert / --key가 필요합니다.')
    context=None
    if a.cert:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(a.cert,a.key)
    host=Host(a.recordings,a.capacity,a.model)
    print('방 코드:',host.code,'\n방장 전용 키 (공유 금지):',host.admin,flush=True)
    web.run_app(host.app(),host=a.bind,port=a.port,ssl_context=context)

if __name__=='__main__': main()
