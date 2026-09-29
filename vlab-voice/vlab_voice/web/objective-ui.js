(() => {
'use strict';
const root=document.getElementById('vlab-voice-app'),$=id=>root.querySelector('#'+id);
const synth=window.speechSynthesis; let armed=false,current=null,epoch=null,seen=new Set(),queue=[],busy=false,active=null,timeout;
const labels={off:'꺼짐',waiting:'게임 감지 대기',tracking:'게임 시간 동기화',disconnected:'게임 연결 끊김',ended:'게임 종료',unsupported:'지원하지 않는 게임'};
const voice=()=>synth?.getVoices().find(v=>v.localService===true&&/^ko(?:[-_]|$)/i.test(v.lang));
function stop(){queue=[];clearTimeout(timeout);active=null;busy=false;synth?.cancel()}
function feedback(text){$('objective-notice').textContent=text}
function drain(){
 if(busy||!queue.length)return;
 const n=queue.shift();if(performance.now()-n.received>5000)return drain();
 const v=voice();if(!v){feedback('설치된 한국어 음성이 없습니다. 운영체제에 한국어 음성을 설치해 주세요.');return}
 const u=new SpeechSynthesisUtterance(n.text);u.voice=v;u.lang=v.lang;u.rate=1.08;
 busy=true;active=u;
 const done=()=>{if(active!==u)return;active=null;busy=false;clearTimeout(timeout);drain()};
 u.onend=done;u.onerror=done;
 timeout=setTimeout(()=>{if(active===u){synth.cancel();done()}},12000);
 synth.speak(u);
}
function say(text){queue.push({text,received:performance.now()});drain()}
function time(t){return Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0')}
function update(data,isAdmin){
 const wasTracking=current?.enabled&&current?.state==='tracking';
 current=data||null;
 const enabled=!!data?.enabled,tracking=enabled&&data?.state==='tracking';
 $('objective-master').disabled=!isAdmin;
 $('objective-profile').disabled=!isAdmin||enabled;
 $('objective-master').textContent=enabled?'팀 알림 끄기 · 방장':'팀 알림 켜기 · 방장';
 $('objective-master').setAttribute('aria-pressed',String(enabled));
 $('objective-apply').disabled=!isAdmin||!tracking;
 $('objective-state').textContent=labels[data?.state]||'꺼짐';
 if(!tracking&&wasTracking)stop();
 if(data&&epoch!==data.epoch){epoch=data.epoch;seen.clear();stop()}
 const cards=$('objective-cards');cards.replaceChildren();
 const rows=data?.rows?.length?data.rows:[{name:'바위게',at:175,key:'scuttle'},{name:'용',at:300,key:'dragon'},{name:'공허 유충',at:480,key:'grubs'},{name:'바론',at:1200,key:'baron'}];
 for(const row of rows){
  const card=document.createElement('div');card.className='objective-card';
  const name=document.createElement('strong');name.textContent=row.name;
  const count=document.createElement('b');count.textContent=tracking?(row.remaining>0?time(row.remaining)+' 남음':'출현 시각 지남'):time(row.at);
  const note=document.createElement('small');note.textContent=(row.source==='visible_timer_manual'?'직접 확인한 시각':row.source==='DragonKill'||row.source==='BaronKill'?'처치 기준 재출현':row.key==='grubs'?'첫 출현 · 재출현 없음':'첫 출현')+' · '+time(row.at);
  card.append(name,count,note);cards.append(card);
 }
 if(data?.warning)feedback(data.warning);
 for(const n of data?.notices||[]){
  if(seen.has(n.id))continue;seen.add(n.id);
  if(!tracking||data.game_time-n.game_time>5||data.game_time<n.game_time)continue;
  feedback(n.text);if(armed)say(n.text);
 }
}
$('objective-voice').onclick=()=>{
 if(!armed&&!voice()){feedback('로컬 한국어 음성을 사용할 수 없습니다. 운영체제 음성 설정을 확인하세요.');return}
 armed=!armed;$('objective-voice').setAttribute('aria-pressed',String(armed));$('objective-voice').textContent=armed?'내 음성 안내 끄기':'내 음성 안내 켜기';
 if(!armed)stop();else say('오브젝트 음성 안내를 켰습니다.');
};
$('objective-test').onclick=()=>{stop();say('용 출현 30초 전입니다.')};
root.objectiveView={update,stop,current:()=>current,feedback};
window.addEventListener('pagehide',stop);update(null,false);
})();
