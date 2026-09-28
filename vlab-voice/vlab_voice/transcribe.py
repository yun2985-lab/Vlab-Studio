"""Retry completed recordings offline, including after Host restart."""
import argparse, json
from pathlib import Path
from .core import Session

def main():
    p=argparse.ArgumentParser();p.add_argument('session_directory');p.add_argument('--model',required=True);a=p.parse_args()
    directory=Path(a.session_directory).resolve();data=json.loads((directory/'session.json').read_text(encoding='utf-8'))
    if data['state'] not in ('recorded','stt_failed'):
        p.error('recorded/stt_failed 세션만 처리합니다. 실행 중인 Host와 동시에 처리하지 마세요.')
    s=Session.__new__(Session);s.directory=directory;s.id=data['session_id'];s.data=data
    s.origin=data['origin_monotonic'];s.tracks={t['user_id']:t for t in data['tracks']};s.writers={}
    for track in s.tracks.values():
        if Path(track['file']).name!=track['file']:p.error('잘못된 트랙 경로')
    s.transcribe(a.model);print(directory/'subtitles.json')

if __name__=='__main__':main()
