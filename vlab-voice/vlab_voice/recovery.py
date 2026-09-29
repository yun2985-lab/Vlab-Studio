"""Restore durable sessions; repair only the fixed PCM WAV format we write."""
import json, math, struct, wave, os
from pathlib import Path
from .core import Session, RATE

class RecordingLock:
    """Prevent a second Host from repairing WAVs still owned by a running Host."""
    def __init__(self,root):
        root=Path(root);root.mkdir(parents=True,exist_ok=True)
        self.file=(root/'.host.lock').open('a+b')
        if self.file.seek(0,2)==0:self.file.write(b'0');self.file.flush()
        self.file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.file.close();raise RuntimeError('같은 녹음 폴더를 사용하는 Voice Host가 이미 실행 중입니다.')
    def close(self):
        if not self.file.closed:self.file.close()

def restore(directory):
    directory=Path(directory)
    data=json.loads((directory/'session.json').read_text(encoding='utf-8'))
    if data.get('schema')!='vlab.voice.session/1' or data.get('session_id')!=directory.name:
        raise ValueError('Invalid saved session')
    s=Session.__new__(Session);s.id=data['session_id'];s.directory=directory;s.data=data
    s.origin=float(data['origin_monotonic']);s.tracks={};s.writers={}
    if not math.isfinite(s.origin):raise ValueError('Invalid saved clock')
    interrupted=data['state'] in ('recording','finalizing','transcribing')
    for track in data['tracks']:
        filename=track['file']
        if Path(filename).name!=filename or not filename.endswith('.wav'):raise ValueError('Invalid track path')
        path=directory/filename
        if interrupted and data['state'] in ('recording','finalizing'):
            with path.open('r+b') as f:
                header=f.read(44)
                if len(header)!=44 or header[:4]!=b'RIFF' or header[8:16]!=b'WAVEfmt ' or header[36:40]!=b'data':
                    raise ValueError('Unrecognized WAV; retained for manual recovery')
                if struct.unpack('<IHHIIHH',header[16:36])!=(16,1,1,RATE,RATE*2,2,16):
                    raise ValueError('Unrecognized PCM format')
                size=(path.stat().st_size-44)//2*2
                if size>0xffffffff-36:raise ValueError('WAV exceeds RIFF size')
                f.seek(4);f.write(struct.pack('<I',36+size));f.seek(40);f.write(struct.pack('<I',size));f.flush()
        with wave.open(str(path),'rb') as w:
            if (w.getnchannels(),w.getsampwidth(),w.getframerate())!=(1,2,RATE):raise ValueError('Invalid PCM')
            track['frames']=w.getnframes()
        s.tracks[track['user_id']]=track
    if interrupted:
        if data['state'] in ('recording','finalizing'):
            data['duration']=max((t['frames']/RATE for t in s.tracks.values()),default=0)
        data['state']='recorded';data['recovery_notice']='이전 실행 중단 후 저장된 음성을 복구했습니다.'
        data.pop('error',None);s.save()
    return s
