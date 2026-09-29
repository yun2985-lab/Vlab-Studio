import tempfile,time,unittest
from pathlib import Path
from aiohttp.test_utils import TestClient,TestServer
from vlab_voice.host import Host

class VideoBridge(unittest.IsolatedAsyncioTestCase):
    async def test_auto_video_clock_and_local_model_readiness(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'host.json';model=None
            host=Host(Path(d)/'recordings',model_path=model,state_file=state)
            async with TestClient(TestServer(host.app())) as client:
                self.assertEqual(state.exists(),True)
                current=time.monotonic();h={'Authorization':'Bearer '+host.admin}
                r=await client.post('/api/control',headers=h,json={'action':'start','auto_from_void_eye':True,'origin_monotonic':current-1,'video':'game.mkv'})
                self.assertEqual(r.status,200,await r.text())
                self.assertEqual(host.session.origin,current-1)
                self.assertEqual(host.session.data['video'],'game.mkv')
                r=await client.post('/api/control',headers=h,json={'action':'stop','end_monotonic':current})
                self.assertEqual(r.status,200,await r.text())
                self.assertAlmostEqual(host.session.data['duration'],1,places=4)
            self.assertFalse(state.exists())
    async def test_auto_flag_and_origin_required_without_host_join(self):
        with tempfile.TemporaryDirectory() as d:
            host=Host(d)
            async with TestClient(TestServer(host.app())) as client:
                h={'Authorization':'Bearer '+host.admin}
                for body in [{'action':'start','origin_monotonic':time.monotonic()},
                             {'action':'start','auto_from_void_eye':True}]:
                    r=await client.post('/api/control',headers=h,json=body)
                    self.assertEqual(r.status,409)
