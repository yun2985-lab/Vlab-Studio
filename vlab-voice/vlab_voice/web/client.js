(() => {
const root=document.getElementById('vlab-voice-app'),v=root.voiceView,$=v.$;
let pc,stream,member,timer,polling=false,admin=false;
async function api(path,body,asAdmin=false){const headers={'Content-Type':'application/json'};if(asAdmin)headers.Authorization='Bearer '+$('key').value;else if(member)headers.Authorization='Bearer '+member.token;const r=await fetch(path,{method:body?'POST':'GET',headers,body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(20000)});if(!r.ok)throw Error(await r.text());return r.json()}
async function poll(){if(!member||polling)return;polling=true;try{const data=await api('/api/status?user_id='+member.user_id);v.state(data,admin);root.objectiveView.update(data.objectives,admin)}catch(e){root.objectiveView.update(null,false);v.notify(e.message,true)}finally{polling=false}}
async function leave(){root.objectiveView.update(null,false);clearInterval(timer);const oldMember=member;member=null;if(pc){pc.onconnectionstatechange=null;pc.close();pc=null}if(stream){stream.getTracks().forEach(t=>t.stop());stream=null}if(oldMember){try{await fetch('/api/leave?user_id='+oldMember.user_id,{method:'POST',headers:{Authorization:'Bearer '+oldMember.token},signal:AbortSignal.timeout(3000)})}catch{}}admin=false;$('join').disabled=false;$('leave').disabled=true;$('mute').disabled=true;$('mute').textContent='마이크 끄기';$('example').disabled=false;$('connection').textContent='퇴장 · 마이크 꺼짐';root.querySelector('.connection-label').classList.remove('connected');v.state({capacity:5,members:[],state:'idle'},false)}
$('join').onclick=async()=>{if(v.isSample())return;if(!$('consent').checked)return v.notify('녹음·전사 안내를 먼저 확인해 주세요.',true);$('join').disabled=true;$('example').disabled=true;
try{stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});pc=new RTCPeerConnection({iceServers:[]});pc.addTrack(stream.getAudioTracks()[0],stream);pc.ontrack=e=>{$('audio').srcObject=new MediaStream([e.track]);$('audio').play().catch(()=>v.notify('통화 수신음의 재생 버튼을 눌러 주세요.'))};pc.onconnectionstatechange=()=>{if(!pc)return;const connected=pc.connectionState==='connected';$('connection').textContent=connected?'음성 연결됨':pc.connectionState==='failed'?'연결 실패 · 재입장 필요':'음성 연결 중';root.querySelector('.connection-label').classList.toggle('connected',connected);if(['failed','disconnected'].includes(pc.connectionState))v.notify('음성 연결이 끊겼습니다. 퇴장 후 다시 입장해 주세요.',true)};
await pc.setLocalDescription(await pc.createOffer());await new Promise((resolve,reject)=>{if(pc.iceGatheringState==='complete')return resolve();const t=setTimeout(()=>reject(Error('연결 정보 수집 시간 초과')),15000);pc.addEventListener('icegatheringstatechange',()=>{if(pc&&pc.iceGatheringState==='complete'){clearTimeout(t);resolve()}})});
admin=!!$('key').value;member=await api('/api/offer',{code:$('code').value.trim().toUpperCase(),name:$('name').value||'참가자',consent:true,sdp:pc.localDescription.sdp},admin);await pc.setRemoteDescription({sdp:member.sdp,type:member.type});$('leave').disabled=false;$('mute').disabled=false;timer=setInterval(poll,500);v.notify('');await poll();
}catch(e){await leave();v.notify(e.message,true)}};
$('leave').onclick=leave;$('mute').onclick=()=>{if(!stream)return;const t=stream.getAudioTracks()[0];t.enabled=!t.enabled;$('mute').textContent=t.enabled?'마이크 끄기':'마이크 켜기'};
for(const action of ['start','stop','transcribe'])$(action).onclick=async()=>{try{await api('/api/control',{action,video:$('videoPath').value},true);await poll()}catch(e){v.notify(e.message,true)}};
$('fetch').onclick=async()=>{try{v.render(await api('/api/subtitles',null,true));v.notify('화자별 자막을 불러왔습니다.')}catch(e){v.notify(e.message,true)}};
$('objective-master').onclick=async()=>{try{
const enabled=!root.objectiveView.current()?.enabled;
if(enabled&&!$('objective-profile').checked)throw Error('일반/랭크 경기인지 확인해 주세요.');
const data=await api('/api/objectives',{enabled,profile:'sr-2026-standard'},true);root.objectiveView.update(data,admin);
}catch(e){root.objectiveView.feedback(e.message)}};
$('objective-apply').onclick=async()=>{try{
const match=/^(\d{1,3}):([0-5]\d)$/.exec($('objective-time').value.trim());
if(!match)throw Error('게임 시각을 분:초 형식으로 입력하세요. 예: 12:35');
const data=await api('/api/objectives',{kind:$('objective-kind').value,spawn_at:Number(match[1])*60+Number(match[2])},true);root.objectiveView.update(data,admin);root.objectiveView.feedback('확인한 출현 시각을 적용했습니다.');
}catch(e){root.objectiveView.feedback(e.message)}};
window.addEventListener('pagehide' ,()=>{if(stream)stream.getTracks().forEach(t=>t.stop());if(pc)pc.close()});
})();
