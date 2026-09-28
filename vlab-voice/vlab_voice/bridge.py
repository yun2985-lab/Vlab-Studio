"""Call from the recorder at first video PTS=0 and after recording stops.
Same PC only: Python time.monotonic is shared across processes on supported OS.
Do not use game-event wall clock as the video origin.
"""
import json, urllib.request

def notify(base_url, admin_key, action, *, video='', origin_monotonic=None, ssl_context=None):
    body=dict(action=action,video=video)
    if origin_monotonic is not None: body['origin_monotonic']=origin_monotonic
    req=urllib.request.Request(base_url.rstrip('/')+'/api/control',
        data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+admin_key})
    with urllib.request.urlopen(req,timeout=3,context=ssl_context) as r:
        return json.load(r)
