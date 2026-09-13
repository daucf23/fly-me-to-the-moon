"""Rebuild the 75-second release cut from the untouched screen recording.

Uses recorded cockpit pixels, so activity and gameplay share exactly the same edit.
Requires ffmpeg, numpy and Pillow. Creates only video/edit-work and video/exports.
The instrumental audio is synthesized here; it is not original game audio.
"""
import argparse
import json
import math
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'video/edit-work/v2'
OUT = ROOT / 'video/exports/v2'
BOLD = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
REGULAR = '/System/Library/Fonts/Supplemental/Arial.ttf'
BG = '#090f19'
WHITE = '#f4f6fb'
MUTED = '#9bacc0'
TEAL = '#77e4ca'
ORANGE = '#ffbc68'
BLUE = '#78c4ff'
# source start, delivered duration, playback speed, title, subtitle, layout, gamma
SHOTS = [
 (1447,3,1,'Meet the\nfly-ght computer.','Three fly models supply steering and throttle.','hook',1.12),
 (27,7,2.5,'I gave them\na rocket.','Three copies of a fruit-fly connectome model.','normal',1.0),
 (60,10,1,'The fly-ght\ncomputer steers.','Jeb and Bill supply the pitch and yaw commands.','mechanism',1.0),
 (148,4,1,'Stage separation.','Jeb: pitch. Bill: yaw. Bob: throttle.','normal',1.08),
 (329,3,1,'Orbit.','Fly models on the controls. SAS off.','normal',1.12),
 (480,4,2,'Next stop:\nthe Mun.','The models fly the instruments.','normal',1.2),
 (522,4,1,'Bob controls\nthe throttle.','Engine power follows his neural output.','power',1.2),
 (898,5,1,'Around the Mun.','232 km flyby on this mission.','normal',1.4),
 (952,4,1,'A long way\nfrom the launchpad.','Same rocket. Same uninterrupted flight.','normal',1.4),
 (1100,7,1,'Now bring\neveryone home.','Guidance sets the burn. The fly models execute it.','normal',1.35),
 (1407,6,1,'Re-entry.','Peak acceleration this mission: 4.5 G.','normal',1.12),
 (1445,6,1,'A very small\nflight crew.','Still aboard. Almost home.','normal',1.12),
 (1587,4,2,'Parachutes.','That is a very welcome sight.','normal',1.5),
 (2045.3,4,1,'And… home.','Parachute touchdown. Normal playback.','landing',1.5),
 (2051,4,1,'Three crew.\nAll home.','One continuous mission. No operator intervention.','end',1.5),
]

def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else REGULAR, size)


def text(d, xy, value, size=28, color=WHITE, bold=False):
    d.text(xy, value, fill=color, font=font(size,bold), spacing=0)


def template(i):
    start,dur,speed,title,subtitle,layout,gamma = SHOTS[i]
    im=Image.new('RGB',(1080,1350),BG);d=ImageDraw.Draw(im)
    d.rectangle((24,26,34,47),fill=TEAL)
    text(d,(46,23),'THE FLY-GHT COMPUTER',23,TEAL,True)
    text(d,(725,23),'ACTUAL KSP FLIGHT',23,MUTED)
    lines=title.split('\n');size=68 if len(lines)>1 else 72
    for j,line in enumerate(lines): text(d,(24,(48+j*74) if len(lines)>1 else 66),line,size,WHITE,True)
    text(d,(26,201),subtitle,29,MUTED)
    if layout in ('mechanism','power'):
        d.rounded_rectangle((24,245,520,1100),radius=18,fill='#101b2a',outline='#29394c',width=2)
        text(d,(50,257),'BOB / THROTTLE' if layout=='power' else 'BILL / YAW',28,TEAL,True)
        for y,n,label,detail in [(325,'01','PIXELS IN','The instrument he sees.'),(475,'02','SPIKES','Recorded neural activity.'),(660,'03',('THROTTLE OUT' if layout=='power' else 'STEERING OUT'),'Orange: model output.\nBlue: actual ship control.')]:
            text(d,(554,y),n,24,TEAL,True)
            text(d,(554,y+33),label,32,WHITE,True)
            text(d,(554,y+78),detail,25,MUTED)
        text(d,(554,800),'THE SAME MOMENT IN KSP',22,TEAL,True)
        text(d,(24,1140),'Pixels → fly model → ' + ('throttle command' if layout=='power' else 'steering command'),37,WHITE,True)
        text(d,(24,1195),'SAS holds attitude during solver searches + time warp.',29,MUTED)
        text(d,(24,1236),'Active control: fly outputs, with gyros and safety logic.',29,MUTED)
    else:
        d.rectangle((22,238,1058,886),outline='#29394c',width=2)
        source=f'{int(start)//60:02}:{int(start)%60:02}'
        label=f'SOURCE {source}   /   {speed:g}× PLAYBACK'
        if layout=='hook': label += '   /   LATER IN THE FLIGHT'
        if layout=='end': label='MISSION RESULTS / SAME CONTINUOUS RUN'
        text(d,(25,901),label,22,MUTED)
        if layout=='end':
            for y,caption,color in [(295,'INSTRUMENT PIXELS',WHITE),(485,'FLY CONNECTOME MODELS',TEAL),(675,'STEERING + THROTTLE',WHITE)]:
                d.rounded_rectangle((24,y,1056,y+120),radius=18,fill='#101b2a',outline='#29394c',width=2)
                box=d.textbbox((0,0),caption,font=font(43,True))
                text(d,((1080-(box[2]-box[0]))/2,y+33),caption,43,color,True)
                if y<675:
                    text(d,(510,y+127),'↓',44,TEAL)
            text(d,(25,830),'Guidance supplies targets. Fly models supply commands.',31,MUTED)
        if layout in ('end','landing'):
            for x,value,label in [(24,'3 / 3','CREW HOME'),(380,'232 km','MUN FLYBY'),(738,'~34 min','ONE FLIGHT')]:
                text(d,(x,991),value,62,TEAL,True)
                text(d,(x,1070),label,24,MUTED,True)
            text(d,(25,1160),'Code + flight evidence',43,WHITE,True)
            text(d,(25,1218),'github.com/daucf23/fly-me-to-the-moon',30,MUTED)
        elif layout=='hook':
            text(d,(25,991),'The flies steer.',45,WHITE,True)
            text(d,(25,1055),'The flies set the throttle.',45,WHITE,True)
            text(d,(25,1160),'Around the Mun. Back to Kerbin.',35,TEAL)
            text(d,(25,1220),'A connectome model for each control axis.',27,MUTED)
        else:
            text(d,(25,956),'FLY-GHT COMPUTER / RECORDED NEURAL ACTIVITY',24,TEAL,True)
            for j,(name,role) in enumerate([('JEB','PITCH'),('BILL','YAW'),('BOB','THROTTLE')]):
                x=24+j*352
                d.rounded_rectangle((x,1004,x+328,1212),radius=14,fill='#101b2a',outline='#29394c',width=1)
                text(d,(x+165,1040),name,32,WHITE,True)
                text(d,(x+165,1083),role,22,TEAL,True)
                text(d,(x+165,1131),'Eye + optic\nlobe sample',21,MUTED)
            text(d,(25,1241),'Fly models: steering + throttle · computer: guidance',29,MUTED)
    # Quiet, consistent bottom rule; each shot advances the chapter progress.
    d.rectangle((24,1315,1056,1318),fill='#29394c')
    path=WORK/f'title-{i:02}.png';im.save(path);return path


def render(i,source,preview=False):
    start,dur,speed,title,subtitle,layout,gamma=SHOTS[i]
    base=template(i);out=WORK/(f'preview-{i:02}.png' if preview else f'shot-{i:02}.mp4')
    # Source pixels are split only after changing time, so every insert stays synced.
    count=2 if layout in ('mechanism','power') else (4 if layout=='normal' else 1)
    streams=''.join(f'[s{j}]' for j in range(count))
    f=[f'[0:v]setpts=(PTS-STARTPTS)/{speed},fps=30,split={count}{streams}'] if count>1 else [f'[0:v]setpts=(PTS-STARTPTS)/{speed},fps=30[s0]']
    if layout in ('mechanism','power'):
        # Bill's entire original column, including both the fly and ship controls.
        seat_x=602 if layout=='power' else 302
        f += [f'[s0]crop=296:496:{seat_x}:112,scale=464:778:flags=lanczos[seat]',
              '[1:v][seat]overlay=40:314:shortest=1[b0]',
              '[s1]crop=1438:896:900:0,scale=480:299:flags=lanczos[game]',
              '[b0][game]overlay=554:829:shortest=1[v]']
    elif layout=='end':
        f += ['[s0]nullsink','[1:v]null[v]']
    else:
        f += [f'[s0]crop=1438:896:900:0,eq=gamma={gamma}:saturation=1.06,scale=1032:644:flags=lanczos[game]',
              '[1:v][game]overlay=24:240:shortest=1[b0]']
        if layout=='normal':
            for j in range(3):
                f += [f'[s{j+1}]crop=84:112:{202+j*300}:125,scale=126:168:flags=neighbor[r{j}]',
                      f'[b{j}][r{j}]overlay={42+j*352}:1024:shortest=1[b{j+1}]']
            f += ['[b3]null[v]']
        else: f += ['[b0]null[v]']
    timeline=sum(s[1] for s in SHOTS[:i])
    f += [f"[v]drawbox=x=24:y=1315:w={round(1032*(timeline+dur)/75)}:h=3:color=0x77e4ca:t=fill[out]"]
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','4','-ss',str(start),'-t',str(dur*speed+.1),'-i',str(source),'-loop','1','-framerate','30','-i',str(base),'-filter_complex_threads','2','-filter_complex',';'.join(f),'-map','[out]','-an']
    if preview:cmd+=['-frames:v','1',str(out)]
    else:cmd+=['-frames:v',str(round(dur*30)),'-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-threads','4','-movflags','+faststart',str(out)]
    subprocess.run(cmd,check=True)
    print(f'{i+1}/{len(SHOTS)} {title.replace(chr(10)," ")} -> {out.name}',flush=True)
    return out


def score():
    """Original quiet space ambience: slow pads and sparse soft tones."""
    sr=48000;length=75;n=sr*length
    audio=np.zeros((n,2),np.float32)
    def add(start,duration,freq,amp,kind='bell',pan=0):
        i=int(start*sr);N=min(int(duration*sr),n-i)
        if N<=0:return
        t=np.arange(N,dtype=np.float32)/sr
        if kind=='pad':
            env=np.minimum(t/1.4,1)*np.minimum((duration-t)/1.8,1)
            v=(np.sin(2*np.pi*freq*t)+.10*np.sin(2*np.pi*freq*2.003*t))*env*.55
        elif kind=='bass':
            env=np.minimum(t/.03,1)*np.exp(-t*3)
            v=np.sin(2*np.pi*freq*t)*env
        else:
            env=np.minimum(t/.18,1)*np.exp(-t*1.8)
            v=(np.sin(2*np.pi*freq*t)+.08*np.sin(2*np.pi*freq*2*t))*env
        v*=amp
        audio[i:i+N,0]+=v*math.sqrt((1-pan)/2)
        audio[i:i+N,1]+=v*math.sqrt((1+pan)/2)
    def hz(m):return 440*2**((m-69)/12)
    chords=[(52,55,59,62),(48,52,55,59),(55,59,62,66),(50,54,57,62)]
    for block,start in enumerate(np.arange(0,66,8.0)):
        chord=chords[block%4]
        for j,m in enumerate(chord):add(start,10,hz(m),.11,'pad',(j-1.5)*.3)
        # Only two soft notes per eight seconds; no fast arpeggio or bass beat.
        for k in range(2):
            at=start+2+k*3.5
            if at<66:add(at,3.0,hz(chord[(block+k*2)%4]+12),.026,'bell',(-1)**k*.25)
    # Deliberate hush during the final approach, then a gentle resolution at contact.
    a,b=int(67*sr),int(70.5*sr);audio[a:b]*=np.linspace(1,.06,b-a)[:,None]
    for j,m in enumerate((52,55,59,64)):
        add(70.5+j*.10,4.5,hz(m),.13,'pad',(j-1.5)*.3)
        add(70.5+j*.10,2,hz(m+12),.02,'bell',(j-1.5)*.2)
    audio[:sr]*=np.linspace(0,1,sr)[:,None]
    audio[-2*sr:]*=np.linspace(1,0,2*sr)[:,None]
    peak=np.max(np.abs(audio));audio*=.68/max(peak,.01)
    path=WORK/'original-score.wav'
    with wave.open(str(path),'wb') as w:
        w.setnchannels(2);w.setsampwidth(2);w.setframerate(sr);w.writeframes((audio*32767).astype('<i2').tobytes())
    return path


def main():
    p=argparse.ArgumentParser();p.add_argument('--preview',action='store_true');p.add_argument('--mux-only',action='store_true');p.add_argument('--shots',nargs='*',type=int);args=p.parse_args()
    WORK.mkdir(exist_ok=True,parents=True);OUT.mkdir(exist_ok=True,parents=True)
    source=next((ROOT/'video').glob('*.mov'))
    indices=args.shots if args.shots is not None else range(len(SHOTS))
    if not args.mux_only:
        for i in indices:render(i,source,args.preview)
    if args.preview or args.shots is not None:return
    score_path=score()
    concat=WORK/'concat.txt';concat.write_text(''.join(f"file 'shot-{i:02}.mp4'\n" for i in range(len(SHOTS))))
    silent=OUT/'fly-ght-computer-twitter-v2-silent.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',str(silent)],check=True)
    final=OUT/'fly-ght-computer-twitter-v2.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(silent),'-i',str(score_path),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-af','loudnorm=I=-25:TP=-3:LRA=9','-t','75','-movflags','+faststart',str(final)],check=True)
    (OUT/'edit-decision-list.json').write_text(json.dumps({'source':str(source.relative_to(ROOT)),'duration':75,'resolution':[1080,1350],'audio':'Quiet original ambient score, -25 LUFS target; no audio in source','sas':'Selected active-flight excerpts have SAS off; solver/warp pauses omitted. End card uses verified results, not SAS-on post-mission footage.','shots':[dict(zip(('source_start','duration','speed','title','subtitle','layout','gamma'),s)) for s in SHOTS]},indent=2))
    print(final,flush=True)

if __name__=='__main__':main()
