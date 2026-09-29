import asyncio,json,tempfile,threading,time,unittest,wave
from pathlib import Path
from unittest.mock import patch
from aiohttp.test_utils import TestClient,TestServer
from vlab_voice.core import Session,atomic
from vlab_voice.host import Host
from vlab_voice.recovery import restore,RecordingLock

class Reliability(unittest.IsolatedAsyncioTestCase):
    async def test_next_recording_during_previous_stt_and_idempotent_stop(self):
        with tempfile.TemporaryDirectory() as root:
            began=threading.Event();release=threading.Event();calls=[]
            def transcribe(s,model):
                calls.append(s.id);s.data['state']='transcribing';s.save();began.set()
                release.wait(5)
                atomic(s.directory/'subtitles.json',dict(session_id=s.id,video=s.data['video']))
                s.data['state']='complete';s.save()
            host=Host(root,model_path=root)
            with patch.object(Session,'transcribe',transcribe):
                async with TestClient(TestServer(host.app())) as c:
                    h={'Authorization':'Bearer '+host.admin}
                    async def start(rid):
                        r=await c.post('/api/control',headers=h,json=dict(action='start',recording_id=rid,video=rid+'.mp4',auto_from_void_eye=True,origin_monotonic=time.monotonic()))
                        self.assertEqual(r.status,200,await r.text());return host.session
                    a=await start('a')
                    r=await c.post('/api/control',headers=h,json=dict(action='stop',recording_id='a',end_monotonic=time.monotonic()))
                    self.assertEqual(r.status,200)
                    for _ in range(100):
                        if began.is_set():break
                        await asyncio.sleep(.01)
                    self.assertTrue(began.is_set())
                    b=await start('b');self.assertNotEqual(a.id,b.id)
                    b.write('voice','speaker',bytes(1920),b.origin)
                    # A retried old stop must never stop the newly recording match.
                    r=await c.post('/api/control',headers=h,json=dict(action='stop',recording_id='a'))
                    self.assertEqual(r.status,200);self.assertEqual(b.data['state'],'recording')
                    duplicate=await start('b');self.assertIs(duplicate,b)
                    release.set();await host.stt_task
                    self.assertEqual(b.data['state'],'recording')
                    r=await c.get('/api/subtitles?session_id='+a.id,headers=h)
                    self.assertEqual((await r.json())['video'],'a.mp4')
                    await c.post('/api/control',headers=h,json=dict(action='stop',recording_id='b'))
                    await host.stt_task;self.assertEqual(calls,[a.id,b.id])

    async def test_start_during_previous_finalize_routes_two_capture_windows(self):
        with tempfile.TemporaryDirectory() as root:
            host=Host(root)
            async with TestClient(TestServer(host.app())) as c:
                h={'Authorization':'Bearer '+host.admin}
                origin=time.monotonic()
                await c.post('/api/control',headers=h,json=dict(action='start',recording_id='a',video='a',auto_from_void_eye=True,origin_monotonic=origin))
                a=host.session
                pending=asyncio.create_task(c.post('/api/control',headers=h,json=dict(action='stop',recording_id='a',end_monotonic=time.monotonic())))
                for _ in range(100):
                    if a.data['state']=='finalizing':break
                    await asyncio.sleep(.01)
                r=await c.post('/api/control',headers=h,json=dict(action='start',recording_id='b',video='b',auto_from_void_eye=True,origin_monotonic=time.monotonic()))
                self.assertEqual(r.status,200);b=host.session
                await pending;self.assertEqual(a.data['state'],'recorded');self.assertEqual(b.data['state'],'recording')

    async def test_restart_resumes_recorded_jobs_and_lists_history(self):
        with tempfile.TemporaryDirectory() as root:
            a=Session(root,'previous.mp4');a.stop()
            a.data['state']='transcribing';a.save()
            def transcribe(s,model):s.data['state']='complete';s.save()
            host=Host(root,model_path=root)
            self.assertEqual(host.session.data['state'],'recorded')
            with patch.object(Session,'transcribe',transcribe):
                async with TestClient(TestServer(host.app())) as c:
                    await host.stt_task
                    self.assertEqual(host.session.data['state'],'complete')
                    r=await c.get('/api/sessions');self.assertEqual(r.status,401)
                    r=await c.get('/api/sessions',headers={'Authorization':'Bearer '+host.admin})
                    data=await r.json();self.assertEqual(data['sessions'][0]['session_id'],a.id)
                    self.assertTrue(data['sessions'][0]['recovery_notice'])

class Recovery(unittest.TestCase):
    def test_second_host_cannot_repair_live_recordings(self):
        with tempfile.TemporaryDirectory() as root:
            lock=RecordingLock(root)
            try:
                with self.assertRaises(RuntimeError):RecordingLock(root)
            finally:lock.close()
            replacement=RecordingLock(root);replacement.close()

    def test_unclean_wav_header_is_repaired_without_changing_pcm(self):
        with tempfile.TemporaryDirectory() as root:
            s=Session(root,'crash.mp4');s.write('a','speaker',b'\x01\x02'*960,s.origin)
            s.write('a','speaker',b'\x03\x04'*960,s.origin+.02)
            writer=s.writers['a'];writer._file.flush();writer._file.close();writer._file=None
            path=s.directory/s.tracks['a']['file'];before=path.read_bytes()[44:]
            recovered=restore(s.directory)
            self.assertEqual(recovered.data['state'],'recorded')
            self.assertEqual(path.read_bytes()[44:],before)
            with wave.open(str(path)) as w:self.assertEqual(w.getnframes(),1920)

if __name__=='__main__':unittest.main()
