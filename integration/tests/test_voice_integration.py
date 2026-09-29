import tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch
from integration.patches.pc.velkozlab_agent.voice_integration import patch_main

class Recorder:
    def start(self,sid):self.final_path=Path('/recordings')/(sid+'.mkv');return 'STARTED'
    def stop(self,sid):return 'STOPPED'
class HookTests(unittest.TestCase):
    def test_same_video_clock_and_stop_even_without_consented_peer(self):
        calls=[]
        ns={'LiveIndexer':lambda catalog,sid,clock,preparer:(sid,clock),'RecordingManager':type('R',(Recorder,),{})}
        patch_main(ns,lambda *args,**kw:calls.append((args,kw)))
        r=ns['RecordingManager']();self.assertEqual(r.start('g1'),'STARTED')
        clock=time.monotonic()-1
        self.assertEqual(ns['LiveIndexer'](None,'g1',clock,None),('g1',clock))
        for _ in range(100):
            if calls:break
            time.sleep(.01)
        self.assertEqual(calls[0][0],('start','/recordings/g1.mkv',clock))
        self.assertEqual(calls[0][1]['recording_id'],'g1')
        self.assertEqual(r.stop('g1'),'STOPPED')
        for _ in range(50):
            if len(calls)==2:break
            time.sleep(.01)
        self.assertEqual(calls[1][0],('stop',))
        self.assertGreaterEqual(calls[1][1]['end_monotonic'],clock)
        self.assertEqual(r.stop('g1'),'STOPPED');self.assertEqual(len(calls),2)
