"""Rebuild the black-and-cyan 16:9 mission cut; preserves all earlier edits."""
import argparse
import json
import math
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw
from edit_twitter_video import ROOT, SHOTS as SOURCE_SHOTS, text, font
BG='#000000'
WHITE='#ffffff'
MUTED='#a0a0a0'
TEAL='#40d9ff'
TITLES=[
 'Meet the “Fly”ght computer: fly models steer this rocket.',
 'Three fruit-fly connectome models take the controls.',
 'Jeb and Bill turn neural spikes into pitch and yaw commands.',
 'The first stage falls away; the fly crew keeps control.',
 'Orbit reached with fly models on pitch, yaw and throttle.',
 'The flight computer plans the burn; the fly models execute it.',
 'Bob’s neural output sets the engine throttle.',
 'The crew passes 232 km above the Mun.',
 'After the Mun flyby, the capsule begins its return to Kerbin.',
 'A return burn puts the capsule on course for entry.',
 'Re-entry pushes the crew to a peak of 4.5 G.',
 'Three fruit-fly connectome models, one very hot capsule.',
 'The parachutes open for the final descent.',
 'Touchdown: all three crew members are home.',
 '“Fly”-by-Wire takes three crew around the Mun and home.',
]
SHOTS=[(*s[:3],TITLES[i],'',*s[5:]) for i,s in enumerate(SOURCE_SHOTS)]

WORK = ROOT / 'video/edit-work/v6'
OUT = ROOT / 'video/exports/v6'


def template(i):
    start,dur,speed,title,subtitle,layout,gamma=SHOTS[i]
    im=Image.new('RGB',(1920,1080),BG);d=ImageDraw.Draw(im)
    # Typographic wordmark: cyan highlights the fly pun without a boxed logo.
    x=24
    for word,color,size in [('“Fly”',TEAL,29),('ght Computer',WHITE,29),('  with  ',MUTED,23),('“Fly”',TEAL,29),('-by-Wire',WHITE,29)]:
        text(d,(x,28 if size==29 else 33),word,size,color,True)
        x+=d.textlength(word,font=font(size,True))
    tag=f'KSP / {speed:g}× PLAYBACK'
    if layout=='hook':tag='KSP / LATER IN THE FLIGHT'
    if layout=='end':tag='ONE CONTINUOUS MISSION'
    w=d.textlength(tag,font=font(20,True))
    text(d,(1896-w,33),tag,20,MUTED,True)
    size=59
    while d.textlength(title,font=font(size,True))>1868:size-=1
    text(d,(24,91),title,size,WHITE,True)
    if layout=='end':
        for x,label in [(80,'INSTRUMENT PIXELS'),(742,'FLY MODELS'),(1350,'SHIP CONTROL')]:
            text(d,(x,248),label,37,WHITE,True)
        text(d,(610,242),'→',49,TEAL,True);text(d,(1220,242),'→',49,TEAL,True)
        d.line((80,332,1840,332),fill='#333333',width=2)
        for x,value,label in [(80,'3 / 3','KERBALS HOME'),(742,'232 km','MUN FLYBY'),(1350,'~34 min','ONE FLIGHT')]:
            text(d,(x,423),value,91,TEAL,True);text(d,(x,542),label,29,WHITE,True)
        text(d,(80,775),'CODE + FLIGHT EVIDENCE',26,MUTED,True)
        text(d,(80,831),'github.com/daucf23/fly-me-to-the-moon',42,WHITE,True)
    else:
        d.rectangle((22,182,1386,1032),outline='#303030',width=2)
        if layout in ('mechanism','power'):
            text(d,(1418,190),'BOB / THROTTLE' if layout=='power' else 'BILL / YAW',31,WHITE,True)
            text(d,(1418,237),'PIXELS → SPIKES → COMMAND',23,TEAL,True)
            d.rectangle((1426,273,1882,952),fill='#0b0b0b')
            text(d,(1418,960),'MODEL OUTPUT → SHIP CONTROL',23,WHITE,True)
            text(d,(1418,997),'SAS HOLD / PLANNING + WARP',18,MUTED,True)
            text(d,(1418,1021),'GYRO + SAFETY AUGMENTATION',18,MUTED,True)
        elif layout=='hook':
            text(d,(1418,220),'3',174,TEAL,True)
            text(d,(1426,410),'FLY MODELS',43,WHITE,True)
            for y,name,role in [(564,'JEB','PITCH'),(674,'BILL','YAW'),(784,'BOB','THROTTLE')]:
                d.line((1426,y-18,1896,y-18),fill='#333333',width=1)
                text(d,(1426,y),name,34,WHITE,True)
                text(d,(1665,y+4),role,27,TEAL,True)
            text(d,(1426,963),'MUN → KERBIN',35,WHITE,True)
        elif layout=='landing':
            for y,value,label in [(250,'3 / 3','KERBALS HOME'),(475,'232 km','MUN FLYBY'),(700,'~34 min','ONE FLIGHT')]:
                text(d,(1440,y),value,67,TEAL,True);text(d,(1442,y+87),label,26,WHITE,True)
            text(d,(1440,982),'PARACHUTE TOUCHDOWN',24,MUTED,True)
        else:
            text(d,(1418,194),'RECORDED NEURAL ACTIVITY',24,WHITE,True)
            text(d,(1418,237),'EYE + OPTIC LOBE SAMPLES',20,MUTED,True)
            for j,(name,role) in enumerate([('JEB','PITCH'),('BILL','YAW'),('BOB','THROTTLE')]):
                y=284+j*216
                d.rectangle((1418,y,1896,y+188),fill='#0b0b0b')
                d.rectangle((1418,y,1421,y+188),fill=TEAL)
                text(d,(1590,y+41),name,36,WHITE,True)
                text(d,(1590,y+100),role,26,TEAL,True)
            text(d,(1418,948),'GUIDANCE / FLIGHT COMPUTER',23,MUTED,True)
            text(d,(1418,994),'CONTROL / FLY MODELS',25,WHITE,True)
    d.rectangle((24,1054,1896,1057),fill='#303030')
    path=WORK/f'title-{i:02}.png';im.save(path);return path


def render(i,source,preview=False):
    start,dur,speed,title,subtitle,layout,gamma=SHOTS[i]
    base=template(i);out=WORK/(f'preview-{i:02}.png' if preview else f'shot-{i:02}.mp4')
    count=2 if layout in ('mechanism','power') else (4 if layout=='normal' else 1)
    streams=''.join(f'[s{j}]' for j in range(count))
    f=[f'[0:v]setpts=(PTS-STARTPTS)/{speed},fps=30,split={count}{streams}'] if count>1 else [f'[0:v]setpts=(PTS-STARTPTS)/{speed},fps=30[s0]']
    if layout=='end': f+=['[s0]nullsink','[1:v]null[v]']
    else:
        f += [f'[s0]crop=1438:896:900:0,eq=gamma={gamma}:saturation=1.06,scale=1360:848:flags=lanczos[game]', '[1:v][game]overlay=24:184:shortest=1[b0]']
        if layout in ('mechanism','power'):
            seat_x=602 if layout=='power' else 302
            f += [f'[s1]crop=296:496:{seat_x}:112,scale=396:664:flags=lanczos[seat]', '[b0][seat]overlay=1456:280:shortest=1[v]']
        elif layout=='normal':
            for j in range(3):
                f += [f'[s{j+1}]crop=84:112:{202+j*300}:125,scale=126:168:flags=neighbor[r{j}]', f'[b{j}][r{j}]overlay=1438:{294+j*216}:shortest=1[b{j+1}]']
            f+=['[b3]null[v]']
        else:f+=['[b0]null[v]']
    timeline=sum(s[1] for s in SHOTS[:i]);f += [f'[v]drawbox=x=24:y=1054:w={round(1872*(timeline+dur)/75)}:h=3:color=0x40d9ff:t=fill[out]']
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','4','-ss',str(start),'-t',str(dur*speed+.1),'-i',str(source),'-loop','1','-framerate','30','-i',str(base),'-filter_complex_threads','2','-filter_complex',';'.join(f),'-map','[out]','-an']
    if preview:cmd+=['-frames:v','1',str(out)]
    else:cmd+=['-frames:v',str(round(dur*30)),'-c:v','libx264','-preset','slow','-crf','16','-pix_fmt','yuv420p','-threads','4','-movflags','+faststart',str(out)]
    subprocess.run(cmd,check=True);print(f'{i+1}/{len(SHOTS)} {title.replace(chr(10)," ")}',flush=True)


from score_mission_v6 import score


def main():
    p=argparse.ArgumentParser();p.add_argument('--preview',action='store_true');p.add_argument('--mux-only',action='store_true');p.add_argument('--shots',nargs='*',type=int);args=p.parse_args()
    WORK.mkdir(exist_ok=True,parents=True);OUT.mkdir(exist_ok=True,parents=True)
    source=next((ROOT/'video').glob('*.mov'))
    if not args.mux_only:
        for i in args.shots if args.shots is not None else range(len(SHOTS)):render(i,source,args.preview)
    if args.preview or args.shots is not None:return
    soundtrack=score()
    concat=WORK/'concat.txt';concat.write_text(''.join(f"file 'shot-{i:02}.mp4'\n" for i in range(len(SHOTS))))
    silent=OUT/'fly-ght-computer-16x9-v6-silent.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',str(silent)],check=True)
    final=OUT/'fly-ght-computer-16x9-v6.mp4'
    # Measure once, then apply a single fixed gain to avoid dynamic gain pumping.
    measured=subprocess.run(['ffmpeg','-hide_banner','-i',str(soundtrack),'-af','loudnorm=I=-22:TP=-2:LRA=15:print_format=json','-f','null','-'],capture_output=True,text=True,check=True).stderr
    stats=json.JSONDecoder().raw_decode(measured[measured.rfind('{'):])[0]
    gain=min(-22-float(stats['input_i']),-2.2-float(stats['input_tp']))
    (OUT/'audio-mastering.json').write_text(json.dumps({'method':'Single constant gain across the entire soundtrack','gain_db':gain,'source_measurement':stats},indent=2))
    mastered=OUT/'soundtrack-master-24bit.wav'
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(soundtrack),'-af',f'volume={gain:.6f}dB','-c:a','pcm_s24le',str(mastered)],check=True)
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(silent),'-i',str(mastered),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','320k','-ar','48000','-t','75','-movflags','+faststart',str(final)],check=True)
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(silent),'-i',str(mastered),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','alac','-movflags','+faststart',str(OUT/'fly-ght-computer-v6-lossless-audio.mov')],check=True)
    (OUT/'edit-decision-list.json').write_text(json.dumps({'source':str(source.relative_to(ROOT)),'duration':75,'resolution':[1920,1080],'audio':'Original arrangement using CC0 VSCO 2 CE acoustic instrument recordings; smooth 112–128 BPM clock; drum-only ending; 24-bit lossless soundtrack and 320 kbps AAC delivery','sas':'Identical v2 SAS-off clip selections. HUD preserved. Final results card replaces SAS-on post-mission footage.','shots':[dict(zip(('source_start','duration','speed','title','subtitle','layout','gamma'),s)) for s in SHOTS]},indent=2))
    print(final,flush=True)

if __name__=='__main__':main()
