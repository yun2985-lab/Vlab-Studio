"""Host clock, isolated WAV tracks and editable subtitle interchange."""
import json, math, os, time, uuid, wave
from pathlib import Path

RATE = 48000

def atomic(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        for attempt in range(8):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.01 * (attempt + 1))
    finally:
        temp.unlink(missing_ok=True)

class Session:
    def __init__(self, root, video, origin=None):
        self.id = uuid.uuid4().hex
        self.directory = Path(root) / self.id
        self.directory.mkdir(parents=True)
        self.origin = time.monotonic() if origin is None else float(origin)
        if not math.isfinite(self.origin) or abs(time.monotonic()-self.origin)>30:
            raise ValueError('녹화 시작 clock은 동일 PC monotonic 기준 최근 30초 이내여야 합니다.')
        self.tracks = {}
        self.writers = {}
        self.data = dict(schema='vlab.voice.session/1', session_id=self.id, video=video,
                         origin_monotonic=self.origin, state='recording', tracks=[],
                         sync_quality='host-receive-anchored; network capture delay not compensated')
        self.save()

    def save(self):
        self.data['tracks'] = list(self.tracks.values())
        atomic(self.directory/'session.json', self.data)

    def write(self, uid, name, pcm, host_time):
        if self.data['state'] not in ('recording','finalizing'):
            return
        target = round((host_time-self.origin)*RATE)
        if target < 0:
            pcm = pcm[min(len(pcm), -target*2):]
            target = 0
        if self.data.get('end_monotonic') is not None:
            last=round((self.data['end_monotonic']-self.origin)*RATE)
            if target>=last: return
            pcm=pcm[:max(0,last-target)*2]
        if not pcm:
            return
        if uid not in self.writers:
            filename = uuid.uuid4().hex+'.wav'
            w = wave.open(str(self.directory/filename), 'wb')
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
            self.writers[uid] = w
            self.tracks[uid] = dict(user_id=uid, speaker=name, file=filename, frames=0)
            self.save()
        w = self.writers[uid]; entry = self.tracks[uid]
        gap = target-entry['frames']
        while gap > 0:
            n = min(gap, RATE)
            w.writeframesraw(bytes(n*2)); entry['frames'] += n; gap -= n
        if gap < 0:
            pcm = pcm[min(len(pcm), -gap*2):]
        if pcm:
            w.writeframesraw(pcm); entry['frames'] += len(pcm)//2

    def begin_finalize(self, end=None):
        if self.data['state'] != 'recording': raise ValueError('녹음 중이 아닙니다.')
        self.data['end_monotonic']=time.monotonic() if end is None else end
        self.data['state']='finalizing'
        self.save()

    def stop(self):
        if self.data['state'] not in ('recording','finalizing'):
            raise ValueError('녹음 중이 아닙니다.')
        for w in self.writers.values(): w.close()
        self.data['state'] = 'recorded'
        self.data['duration'] = self.data.get('end_monotonic',time.monotonic())-self.origin
        self.save()

    def transcribe(self, model_path, model_factory=None):
        if self.data['state'] not in ('recorded', 'stt_failed'):
            raise ValueError('게임 종료 후에만 전사할 수 있습니다.')
        self.data['state'] = 'transcribing'; self.save()
        try:
            if model_factory is None:
                from faster_whisper import WhisperModel
                model_factory = WhisperModel
            model = model_factory(str(model_path), device='cpu', compute_type='int8',
                                  cpu_threads=2, local_files_only=True)
            result = dict(schema='vlab.voice.subtitles/1', session_id=self.id,
                          video=self.data['video'], timebase='video_seconds', tracks=[])
            for track in self.tracks.values():
                segments, _ = model.transcribe(str(self.directory/track['file']), language='ko',
                                                vad_filter=True, condition_on_previous_text=False)
                clips = [dict(id=uuid.uuid4().hex, start=float(s.start), end=float(s.end),
                              text=s.text.strip()) for s in segments if s.text.strip()]
                result['tracks'].append(dict(user_id=track['user_id'], speaker=track['speaker'],
                                             audio=track['file'], clips=clips))
            atomic(self.directory/'subtitles.json', result)
            self.data['state'] = 'complete'; self.data.pop('error', None); self.save()
            return result
        except Exception as e:
            self.data['state'] = 'stt_failed'; self.data['error'] = str(e); self.save()
            raise
