"""Objective schedule from official local Live Client Data snapshots.
No memory reads, injection, packet capture, OCR or inferred fog-of-war information.
"""
import asyncio
import math
import time
import uuid
from collections import Counter
from aiohttp import ClientSession, ClientTimeout

PROFILE = 'sr-2026-standard'
FIRST = {'scuttle':175, 'dragon':300, 'grubs':480, 'baron':1200}
NAMES = {'scuttle':'바위게','scuttle_top':'위쪽 바위게','scuttle_bottom':'아래쪽 바위게',
         'dragon':'용','elder':'장로 드래곤','grubs':'공허 유충','baron':'바론'}
RESPAWN = {'dragon':300,'baron':360,'elder':360}
ELEMENTS = {'Air','Earth','Fire','Water','Hextech','Chemtech'}

def seconds(value):
    value=float(value)
    if not math.isfinite(value) or value < 0: raise ValueError('게임 시간이 올바르지 않습니다.')
    return value

class ObjectiveClock:
    def __init__(self):
        self.enabled=False; self.reset()

    def reset(self):
        self.epoch=uuid.uuid4().hex; self.last=None; self.game_time=None
        self.seen=set(); self.manual={}; self.notices=[]; self.rows=[]
        self.state='waiting'; self.warning=''; self.last_received=0.0

    def enable(self, enabled):
        if not isinstance(enabled,bool): raise ValueError('enabled는 boolean이어야 합니다.')
        self.enabled=enabled; self.last=None; self.notices=[]
        if not enabled: self.state='off'
        else: self.state='waiting'

    def unavailable(self):
        self.state='waiting' if self.game_time is None else 'disconnected'
        self.last=None; self.notices=[]

    def schedule_visible(self, kind, target):
        if self.state!='tracking' or time.monotonic()-self.last_received>5:
            raise ValueError('실시간 게임 연결 후 게임 화면에서 확인한 시간을 입력하세요.')
        if kind not in NAMES or kind in ('scuttle','grubs'):
            raise ValueError('이 오브젝트는 수동 보정 대상이 아닙니다.')
        target=seconds(target)
        if not self.game_time < target <= self.game_time+900:
            raise ValueError('현재 게임 시간 이후 15분 이내의 출현 시각을 입력하세요.')
        if kind in ('dragon','elder'):
            self.manual.pop('dragon',None);self.manual.pop('elder',None)
        self.manual[kind]=dict(key=kind, name=NAMES[kind], at=target, source='visible_timer_manual',
                               observed_at=self.game_time, cycle='manual:'+str(target))

    def feed(self, stats, events, players):
        now=seconds(stats['gameTime'])
        if stats.get('mapNumber')!=11 or stats.get('gameMode')!='CLASSIC':
            self.state='unsupported';self.last=None;self.notices=[];self.rows=[];return []
        # Live data does not provide a reliable queue identifier. Profile is explicitly standard SR only.
        if self.game_time is not None and (now<self.game_time-3 or (self.last_received and time.monotonic()-self.last_received>15)):
            self.reset()
        self.last_received=time.monotonic(); self.game_time=now
        if not self.enabled: self.last=now;self.state='off';return []
        valid=[]
        for e in events:
            if not isinstance(e,dict):continue
            try: stamp=seconds(e.get('EventTime'))
            except (TypeError,ValueError):continue
            if stamp<=now+.1:valid.append(e)
        valid.sort(key=lambda e:float(e['EventTime']))
        if any(e.get('EventName')=='GameEnd' for e in valid):
            self.state='ended';self.rows=[];self.notices=[];self.last=now;return []
        self.state='tracking';self.warning=''
        plans={k:dict(key=k,name=NAMES[k],at=at,source='fixed_first_spawn',cycle='first') for k,at in FIRST.items()}
        kills=[e for e in valid if e.get('EventName') in ('DragonKill','BaronKill')]
        # Duplicate snapshots or duplicate entries cannot increment soul stacks.
        kills=list({(e.get('EventID'),e['EventName'],e['EventTime']):e for e in kills}.values())
        barons=[e for e in kills if e['EventName']=='BaronKill']
        if barons:
            e=barons[-1];at=float(e['EventTime'])
            plans['baron']=dict(key='baron',name=NAMES['baron'],at=at+RESPAWN['baron'],source='BaronKill',cycle=str(at))
        dragons=[e for e in kills if e['EventName']=='DragonKill']
        if dragons:
            e=dragons[-1];at=float(e['EventTime']);kind=e.get('DragonType')
            teams={}
            for p in players:
                if not isinstance(p,dict):continue
                if p.get('team') not in ('ORDER','CHAOS'):continue
                for field in ('summonerName','riotId','riotIdGameName'):
                    if p.get(field):teams.setdefault(p[field],set()).add(p['team'])
            counts=Counter();complete=any(e.get('EventName')=='GameStart' for e in valid)
            for d in dragons:
                if d.get('DragonType')=='Elder':continue
                matches=teams.get(d.get('KillerName'),set())
                if len(matches)!=1 or d.get('DragonType') not in ELEMENTS:complete=False
                else:counts[next(iter(matches))]+=1
            if kind=='Elder':target_kind='elder'
            elif kind in ELEMENTS and complete:target_kind='elder' if max(counts.values(),default=0)>=4 else 'dragon'
            else:target_kind=None
            plans.pop('dragon',None)
            if target_kind:
                plans[target_kind]=dict(key=target_kind,name=NAMES[target_kind],at=at+RESPAWN[target_kind],source='DragonKill',cycle=str(at))
            else:self.warning='용 처치 팀/전체 이력이 불완전하여 다음 용 알림을 보류했습니다. 게임 내 타이머로 보정하세요.'
        # A new observed kill overrides an older manual timer for that camp.
        for key,p in list(self.manual.items()):
            relevant=barons if key=='baron' else dragons if key in ('dragon','elder') else []
            if relevant and float(relevant[-1]['EventTime'])>p['observed_at']:
                self.manual.pop(key,None);continue
            if key in ('dragon','elder'):
                plans.pop('dragon',None);plans.pop('elder',None)
            plans[key]=p
        previous=now-.001 if self.last is None else self.last
        # Reconnects/clock jumps must not replay outdated spoken instructions.
        continuous=0<=now-previous<=5
        emitted=[]
        for p in plans.values():
            phases=[('spawn',p['at'])]
            if p['key'] not in ('scuttle','scuttle_top','scuttle_bottom'):phases.insert(0,('warning',p['at']-30))
            for phase,when in phases:
                ident=f"{self.epoch}:{p['key']}:{p['cycle']}:{phase}"
                if previous<when<=now and continuous and now-when<=2 and ident not in self.seen:
                    self.seen.add(ident)
                    text=(f"{p['name']} 출현 30초 전입니다." if phase=='warning' else
                          f"{p['name']}가 출현했습니다." if p['key'].startswith('scuttle') else
                          f"커피 사고 싶지 않으면 {p['name']}으로 당장 튀어와.")
                    emitted.append(dict(id=ident,epoch=self.epoch,kind=p['key'],phase=phase,text=text,
                                        game_time=when,created_at=time.time(),expires_at=time.time()+5))
        self.notices=(self.notices+emitted)[-20:]
        self.rows=[dict(p,remaining=round(p['at']-now,1),status='scheduled' if p['at']>now else
                       ('first_only' if p['key'] in ('scuttle','grubs') else 'spawn_time_passed')) for p in plans.values()]
        self.last=now
        return emitted

    def status(self):
        return dict(enabled=self.enabled,profile=PROFILE,state=self.state,epoch=self.epoch,
                    game_time=self.game_time,rows=self.rows,notices=[n for n in self.notices if n['expires_at']>time.time()],warning=self.warning,
                    source='방장 PC · 공식 Live Client Data API',scuttle_respawn='visible timer manual only',
                    grubs_respawn=False)

class ObjectiveService:
    """Only reads fixed loopback endpoints; no arbitrary URLs or game-process access."""
    def __init__(self):
        self.clock=ObjectiveClock(); self.task=None
    async def start(self,app): self.task=asyncio.create_task(self.run())
    async def close(self,app):
        if self.task:
            self.task.cancel()
            try:await self.task
            except asyncio.CancelledError:pass
    async def run(self):
        async with ClientSession(timeout=ClientTimeout(total=2),trust_env=False) as client:
            async def get(endpoint):
                # Riot documents the game's self-signed localhost certificate.
                async with client.get('https://127.0.0.1:2999/liveclientdata/'+endpoint,
                                      ssl=False,allow_redirects=False) as r:
                    r.raise_for_status();return await r.json(content_type=None)
            while True:
                if self.clock.enabled:
                    try:
                        stats,events,players=await asyncio.gather(get('gamestats'),get('eventdata'),get('playerlist'))
                        self.clock.feed(stats,events['Events'],players)
                    except (OSError,ValueError,KeyError,TypeError,asyncio.TimeoutError): self.clock.unavailable()
                    except Exception: self.clock.unavailable()
                await asyncio.sleep(.5)
