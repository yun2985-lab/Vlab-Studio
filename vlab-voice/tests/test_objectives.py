import unittest,time,tempfile
from aiohttp.test_utils import TestClient,TestServer
from vlab_voice.objectives import ObjectiveClock,FIRST,PROFILE
from vlab_voice.host import Host

START={'EventID':0,'EventName':'GameStart','EventTime':0}
PLAYERS=[dict(summonerName='host',team='ORDER'),dict(summonerName='enemy',team='CHAOS')]
def kill(at,kind='DragonKill',dragon='Fire',who='host',id=None):
    return dict(EventID=id or at,EventName=kind,EventTime=at,DragonType=dragon,KillerName=who)
class Objectives(unittest.TestCase):
    def setUp(self):self.c=ObjectiveClock();self.c.enable(True)
    def feed(self,t,events=None,players=None,**extra):
        return self.c.feed(dict(gameTime=t,mapNumber=11,gameMode='CLASSIC',**extra),events or [START],players or PLAYERS)
    def cross(self,t,events=None):
        self.feed(t-.5,events);return self.feed(t+.2,events)
    def test_all_first_spawns_and_text(self):
        for kind,at in FIRST.items():
            if kind!='scuttle':
                out=self.cross(at-30);self.assertEqual([(x['kind'],x['phase']) for x in out],[(kind,'warning')])
                self.assertIn('출현 30초 전입니다.',out[0]['text'])
            out=self.cross(at);self.assertEqual([(x['kind'],x['phase']) for x in out],[(kind,'spawn')])
            if kind!='scuttle':self.assertIn('커피 사고 싶지 않으면',out[0]['text'])
    def test_dragon_and_baron_kill_based_respawns(self):
        for event,at,respawn,key in [('DragonKill',420,300,'dragon'),('BaronKill',1500,360,'baron')]:
            es=[START,kill(at,kind=event)]
            out=self.cross(at+respawn-30,es);self.assertEqual(out[0]['kind'],key)
            self.assertEqual(out[0]['phase'],'warning')
            out=self.cross(at+respawn,es);self.assertEqual(out[0]['phase'],'spawn')
            self.assertEqual(self.feed(at+respawn+.5,es),[])
    def test_grubs_no_second_spawn_scuttle_manual(self):
        self.feed(500);self.feed(900)
        rows={r['key']:r for r in self.c.rows}
        self.assertEqual(rows['grubs']['at'],480);self.assertEqual(rows['scuttle']['at'],175)
        self.c.schedule_visible('scuttle_top',950)
        self.assertEqual(self.cross(950)[0]['kind'],'scuttle_top')
        with self.assertRaises(ValueError):self.c.schedule_visible('grubs',1000)
    def test_soul_and_elder_with_duplicate_history(self):
        es=[START]+[kill(at,id=i+1) for i,at in enumerate([350,680,1010,1340])]
        es+=es[1:]
        out=self.cross(1670,es);self.assertEqual(out[0]['kind'],'elder')
        es.append(kill(1740,dragon='Elder',id=9))
        self.assertEqual(self.cross(2070,es)[0]['kind'],'elder')
    def test_split_teams_do_not_trigger_soul(self):
        es=[START]+[kill(at,who='host' if i%2 else 'enemy') for i,at in enumerate([350,680,1010,1340])]
        self.feed(1350,es);self.assertEqual(next(r for r in self.c.rows if r['key']=='dragon')['at'],1640)
    def test_missing_history_or_unknown_team_suspends_dragon(self):
        for es in [[kill(350)],[START,kill(350,who='unknown')]]:
            self.feed(400,es);self.assertNotIn('dragon',[r['key'] for r in self.c.rows]);self.assertTrue(self.c.warning)
    def test_manual_override_then_new_kill_wins(self):
        self.feed(400,[START,kill(350,who='unknown')]);self.c.schedule_visible('dragon',600)
        self.c.schedule_visible('elder',700);self.assertNotIn('dragon',self.c.manual)
        self.feed(450,[START,kill(440)]);self.assertFalse(self.c.manual)
        self.assertEqual(next(r for r in self.c.rows if r['key']=='dragon')['at'],740)
    def test_no_old_notices_after_jumps_disconnect_toggle(self):
        self.feed(250);self.assertEqual(self.feed(290),[])
        self.c.unavailable();self.assertEqual(self.feed(301),[])
        self.c.enable(False);self.assertEqual(self.feed(450),[])
        self.c.enable(True);self.assertEqual(self.feed(481),[])
        self.assertEqual(self.c.notices,[])
    def test_new_game_end_unsupported(self):
        self.feed(100);epoch=self.c.epoch;self.feed(0);self.assertNotEqual(epoch,self.c.epoch)
        self.feed(200,[START,dict(EventName='GameEnd',EventTime=199)]);self.assertEqual(self.c.state,'ended')
        self.c.feed(dict(gameTime=0,mapNumber=12,gameMode='ARAM'),[],[])
        self.assertEqual(self.c.state,'unsupported');self.assertEqual(self.c.rows,[])
    def test_expired_notice_filtered_and_input_checks(self):
        self.cross(270);self.c.notices[0]['expires_at']=time.time()-1
        self.assertEqual(self.c.status()['notices'],[])
        for t in [0,270,float('nan'),float('inf'),2000]:
            with self.assertRaises(ValueError):self.c.schedule_visible('dragon',t)
        self.c.unavailable()
        with self.assertRaises(ValueError):self.c.schedule_visible('dragon',300)
        with self.assertRaises(ValueError):self.c.enable('true')

class Control(unittest.IsolatedAsyncioTestCase):
    async def test_authorization_and_explicit_profile(self):
        with tempfile.TemporaryDirectory() as d:
            host=Host(d)
            async with TestClient(TestServer(host.app())) as client:
                r=await client.post('/api/objectives',json=dict(enabled=True,profile=PROFILE));self.assertEqual(r.status,401)
                h={'Authorization':'Bearer '+host.admin}
                r=await client.post('/api/objectives',headers=h,json=dict(enabled=True));self.assertEqual(r.status,400)
                r=await client.post('/api/objectives',headers=h,json=dict(enabled=True,profile=PROFILE));self.assertEqual(r.status,200)
                self.assertTrue((await r.json())['enabled'])
                r=await client.post('/api/objectives',headers=h,json=dict(enabled=False,profile=PROFILE));self.assertEqual(r.status,200)
                self.assertFalse(host.status()['objectives']['enabled'])
                r=await client.post('/api/objectives',headers=h,json=dict(kind='baron',spawn_at=1000));self.assertEqual(r.status,400)
