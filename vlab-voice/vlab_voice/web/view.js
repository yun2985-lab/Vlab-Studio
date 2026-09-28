(() => {
  const root=document.getElementById('vlab-voice-app');
  const $=id=>root.querySelector('#'+id);
  let documentData=null, selected=null, duration=60, sample=false, videoURL=null;
  const clock=(seconds,full=false)=>{seconds=Math.max(0,Number(seconds)||0);const s=Math.floor(seconds);return (full?String(Math.floor(s/3600)).padStart(2,'0')+':':'')+String(Math.floor(s/60)%60).padStart(2,'0')+':'+String(s%60).padStart(2,'0')};
  const make=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el};
  function notify(message,isError=false){$('notice').hidden=!message;$('notice').textContent=message;$('notice').classList.toggle('error',isError)}
  function people(members=[],capacity=5){
    $('member-count').textContent=members.length+' / '+capacity;$('members').replaceChildren();
    for(let i=0;i<capacity;i++){
      const m=members[i], row=make('div','person'+(!m?' empty-person':'')+(m&&m.level>.03?' speaking':''));
      row.append(make('span','avatar',m?m.name.slice(0,2):'+'));
      const info=make('div','person-info');info.append(make('span','person-name',m?m.name:'참가 대기'));
      info.append(make('span','person-meta',m?(m.host?'방장 · ':'')+(m.connection==='connected'?(m.level>.03?'음성 입력 중':'연결됨'):'연결 중'):'빈자리'));
      row.append(info);const meter=make('span','mic-meter');meter.setAttribute('aria-label',m&&m.level>.03?'음성 입력 감지':'음성 입력 없음');
      for(let j=0;j<5;j++)meter.append(make('i'));row.append(meter);$('members').append(row);
    }
  }
  function state(s,admin=false){
    people(s.members,s.capacity);
    const names={idle:'녹음 대기',recording:'개별 음성 녹음 중',finalizing:'마지막 음성 저장 중',recorded:'녹음 완료 · 전사 대기',transcribing:'로컬 전사 중',complete:'자막 생성 완료',stt_failed:'전사 실패',recording_failed:'녹음 실패'};
    $('status').textContent=names[s.state]||s.state;$('elapsed').textContent=clock(s.elapsed,true);$('track-count').textContent=(s.recorded_tracks||0)+'개';
    $('model-status').textContent=s.model_ready?'경로 지정됨':'모델 미지정';$('record-dot').classList.toggle('active',s.state==='recording'||s.state==='transcribing');
    $('start').disabled=!admin||['recording','finalizing','transcribing'].includes(s.state);$('stop').disabled=!admin||s.state!=='recording';
    $('transcribe').disabled=!admin||!s.model_ready||!['recorded','stt_failed'].includes(s.state);$('fetch').disabled=!admin||s.state!=='complete';
    if(s.error)notify(s.error,true);
  }
  function validate(data){
    if(data.schema!=='vlab.voice.subtitles/1'||!Array.isArray(data.tracks)||data.tracks.length>100)throw Error('지원하지 않는 자막 형식입니다.');
    for(const t of data.tracks){if(typeof t.speaker!=='string'||!Array.isArray(t.clips)||t.clips.length>10000)throw Error('잘못된 화자 트랙입니다.');
      for(const c of t.clips)if(typeof c.text!=='string'||!Number.isFinite(c.start)||!Number.isFinite(c.end)||c.start<0||c.end<=c.start)throw Error('자막의 문구 또는 시간이 올바르지 않습니다.');}
    return data;
  }
  function render(data){documentData=JSON.parse(JSON.stringify(validate(data)));selected=null;$('caption-editor').hidden=true;draw();$('save').disabled=false;}
  function draw(){
    const tracks=documentData?documentData.tracks:Array.from({length:5},(_,i)=>({speaker:'음성 트랙 '+(i+1),clips:[]}));
    duration=Math.max(15,...tracks.flatMap(t=>t.clips.map(c=>c.end)))*1.08;
    if(!documentData)duration=60;
    $('ruler').replaceChildren();for(let i=0;i<5;i++)$('ruler').append(make('span','',clock(duration*i/4)));
    $('lanes').replaceChildren();let total=0;
    tracks.forEach((t,ti)=>{const lane=make('div','lane');const label=make('div','lane-label',t.speaker);label.append(make('small','',String(t.clips.length).padStart(2,'0')+' SUBTITLES'));lane.append(label);
      const line=make('div','lane-track');if(!t.clips.length)line.append(make('span','empty-track','자막 대기'));
      t.clips.forEach((c,ci)=>{total++;const button=make('button','caption-clip'+(selected&&selected.ti===ti&&selected.ci===ci?' selected':''),c.text);button.type='button';button.style.left=(c.start/duration*100)+'%';button.style.width=((c.end-c.start)/duration*100)+'%';button.setAttribute('aria-label',`${t.speaker}, ${c.start}초부터 ${c.end}초: ${c.text}`);button.onclick=()=>select(ti,ci);line.append(button)});lane.append(line);$('lanes').append(lane)});
    $('caption-summary').textContent=documentData?`${tracks.length}개 화자 트랙 · ${total}개 자막 · 자막을 눌러 편집`:'자막이 아직 없습니다. 전사 결과를 가져오거나 JSON 파일을 여세요.';
  }
  function select(ti,ci){selected={ti,ci};const t=documentData.tracks[ti],c=t.clips[ci];$('editor-speaker').textContent=t.speaker+' · 자막 편집';$('caption-start').value=c.start;$('caption-end').value=c.end;$('caption-text').value=c.text;$('caption-editor').hidden=false;draw()}
  function edit(){if(!selected)return;const c=documentData.tracks[selected.ti].clips[selected.ci],start=Number($('caption-start').value),end=Number($('caption-end').value);
    if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start){notify('시작 시간은 0 이상, 종료 시간은 시작보다 커야 합니다.',true);return false;}
    c.start=start;c.end=end;c.text=$('caption-text').value;notify('');draw();return true;
  }
  for(const id of ['caption-start','caption-end','caption-text'])$(id).addEventListener('input',edit);
  $('jump').onclick=()=>{if(!selected)return;if(!$('video').src)return notify('먼저 로컬 영상을 선택해 주세요.');$('video').currentTime=documentData.tracks[selected.ti].clips[selected.ci].start};
  $('load').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>5000000)throw Error('자막 파일은 5MB 이하로 선택하세요.');render(JSON.parse(await file.text()));notify('자막 파일을 불러왔습니다.')}catch(e){notify(e.message,true)}};
  $('save').onclick=()=>{if(!documentData)return;if(selected&&edit()===false)return;if(root.dataset.inline==='true')return notify('예시: 수정된 자막을 JSON으로 저장합니다.');const url=URL.createObjectURL(new Blob([JSON.stringify(documentData,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='vlab-voice-subtitles-edited.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notify('수정한 자막을 저장했습니다.')};
  $('videoFile').onchange=e=>{const f=e.target.files[0];if(!f)return;if(videoURL)URL.revokeObjectURL(videoURL);videoURL=URL.createObjectURL(f);$('video').src=videoURL;$('video').hidden=false;$('video-empty').hidden=true;$('video-name').textContent=f.name;$('video-badge').textContent='로컬 영상';};
  $('video').ontimeupdate=()=>{$('video-time').textContent=clock($('video').currentTime)+' / '+clock($('video').duration)};
  const demoMembers=['Jason','참가자 2','참가자 3','참가자 4','참가자 5'].map((name,i)=>({name,user_id:'demo-'+i,host:i===0,connection:'connected',level:0}));
  const demoCaptions={schema:'vlab.voice.subtitles/1',session_id:'UI-SAMPLE-ONLY',timebase:'video_seconds',tracks:[
    {speaker:'Jason',user_id:'demo-0',clips:[{id:'a',start:1,end:12,text:'용 쪽으로 먼저 이동할게.'},{id:'b',start:28,end:43,text:'시야 확인하고 같이 들어가자.'}]},
    {speaker:'참가자 2',user_id:'demo-1',clips:[{id:'c',start:6,end:20,text:'나도 바로 합류할 수 있어.'},{id:'d',start:44,end:59,text:'뒤쪽은 내가 확인할게.'}]},
    {speaker:'참가자 3',user_id:'demo-2',clips:[{id:'e',start:15,end:31,text:'여기 와드 하나 설치했어.'}]},
    {speaker:'참가자 4',user_id:'demo-3',clips:[{id:'f',start:24,end:38,text:'상대 정글이 아직 안 보여.'}]},
    {speaker:'참가자 5',user_id:'demo-4',clips:[{id:'g',start:38,end:54,text:'확인했어. 천천히 같이 가자.'}]}]};
  function demo(){sample=true;root.dataset.demo='true';$('demo-banner').hidden=false;$('name').value='Jason';$('code').value='SAMPLE-5';$('connection').textContent='화면 예시 · 5명';root.querySelector('.connection-label').classList.add('connected');$('join').disabled=true;
    state({capacity:5,members:demoMembers,state:'complete',elapsed:60,recorded_tracks:5,model_ready:true},false);render(demoCaptions);select(0,0);$('model-status').textContent='예시 상태';$('room-summary').textContent='예시 방 · 실제 연결 아님';notify('');
  }
  function reset(){sample=false;delete root.dataset.demo;$('demo-banner').hidden=true;documentData=null;selected=null;$('caption-editor').hidden=true;$('save').disabled=true;draw();state({capacity:5,members:[],state:'idle'},false);$('name').value='';$('code').value='';$('join').disabled=false;$('connection').textContent='연결 대기';root.querySelector('.connection-label').classList.remove('connected');$('room-summary').textContent='방장 PC 주소에서 코드로 입장';notify('')}
  $('example').onclick=demo;$('exit-demo').onclick=reset;
  root.voiceView={$,notify,people,state,render,demo,reset,isSample:()=>sample};
  people();draw();
})();
