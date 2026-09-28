"""Windows entry point for the standalone VLab Voice Host application."""
import os
import sys
import threading
import webbrowser
from pathlib import Path
from vlab_voice.host import main

if __name__ == '__main__':
    if '--recordings' not in sys.argv:
        base = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'VLab Voice' / 'recordings'
        base.mkdir(parents=True, exist_ok=True)
        sys.argv.extend(['--recordings', str(base)])
    if '--model' not in sys.argv and os.environ.get('VLAB_VOICE_MODEL'):
        sys.argv.extend(['--model', os.environ['VLAB_VOICE_MODEL']])
    if '--no-browser' in sys.argv:
        sys.argv.remove('--no-browser')
    else:
        threading.Timer(3.0, lambda: webbrowser.open('http://127.0.0.1:8790')).start()
    main()
