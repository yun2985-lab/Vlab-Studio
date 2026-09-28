"""Map independent voice captions through existing clip_core cut rows.
Returns a sidecar; does not mutate a VLab project or burn text into a video.
"""
import copy, math, uuid

def through_cuts(subtitles, cuts):
    out=copy.deepcopy(subtitles)
    out['schema']='vlab.voice.subtitles/1'
    out['timebase']='edited_video_seconds'
    for track in out['tracks']:track['clips']=[]
    cursor=0.0
    for cut in cuts:
        start,end=float(cut['start']),float(cut['end'])
        if not all(map(math.isfinite,[start,end])) or not 0<=start<end:
            raise ValueError('Invalid cut')
        for original,target in zip(subtitles['tracks'],out['tracks']):
            for caption in original['clips']:
                left=max(start,float(caption['start']));right=min(end,float(caption['end']))
                if left<right:
                    item=copy.deepcopy(caption)
                    item.update(id=uuid.uuid4().hex,source_caption_id=caption['id'],
                                start=cursor+left-start,end=cursor+right-start)
                    target['clips'].append(item)
        cursor+=end-start
    out['duration']=cursor
    return out
