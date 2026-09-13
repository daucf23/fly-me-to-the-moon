"""Rebuild the 16:9, original percussion-score cut; preserves both earlier edits."""
import argparse
import json
import math
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw
from edit_twitter_video import ROOT, SHOTS, BG, WHITE, MUTED, TEAL, text, font

WORK = ROOT / 'video/edit-work/v3'
OUT = ROOT / 'video/exports/v3'


def template(i):
    start,dur,speed,title,subtitle,layout,gamma=SHOTS[i]
    im=Image.new('RGB',(1920,1080),BG);d=ImageDraw.Draw(im)
    d.rectangle((24,25,34,46),fill=TEAL)
    text(d,(48,22),'THE FLY-GHT COMPUTER',23,TEAL,True)
    text(d,(1610,22),'ACTUAL KSP FLIGHT',23,MUTED)
    text(d,(24,55),title.replace('\n',' '),62,WHITE,True)
    text(d,(27,124),subtitle,29,MUTED)
    text(d,(27,158),f'SOURCE {int(start)//60:02}:{int(start)%60:02} / {speed:g}× PLAYBACK'+(' / LATER IN THE FLIGHT' if layout=='hook' else ''),15,MUTED)
    if layout=='end':
        d.rectangle((24,155,850,179),fill=BG)
        text(d,(27,164),'MISSION RESULTS / SAME CONTINUOUS RUN',19,TEAL)
        for x,number,label,detail in [(24,'01','INSTRUMENT PIXELS','Guidance supplies targets.'),(660,'02','FLY CONNECTOME MODELS','Neural activity becomes commands.'),(1296,'03','STEERING + THROTTLE','The rocket responds.')]:
            d.rounded_rectangle((x,248,x+600,488),radius=18,fill='#101b2a',outline='#29394c',width=2)
            text(d,(x+28,274),number,29,TEAL,True)
            text(d,(x+28,335),label,32,WHITE,True)
            text(d,(x+28,410),detail,27,MUTED)
        for x,value,label in [(80,'3 / 3','CREW HOME'),(718,'232 km','MUN FLYBY'),(1370,'~34 min','ONE FLIGHT')]:
            text(d,(x,571),value,87,TEAL,True);text(d,(x,680),label,29,MUTED,True)
        text(d,(80,829),'Code + flight evidence',42,WHITE,True)
        text(d,(80,893),'github.com/daucf23/fly-me-to-the-moon',35,MUTED)
    else:
        d.rectangle((22,182,1386,1032),outline='#29394c',width=2)
        if layout in ('mechanism','power'):
            text(d,(1418,184),'BOB / THROTTLE' if layout=='power' else 'BILL / YAW',31,TEAL,True)
            text(d,(1418,229),'Pixels → fly model → command',24,WHITE,True)
            d.rounded_rectangle((1426,272,1882,952),radius=15,fill='#101b2a',outline='#29394c',width=2)
            text(d,(1418,962),'Orange: fly output. Blue: ship control.',23,MUTED)
            text(d,(1418,1000),'With gyros + safety logic.',23,MUTED)
            # Explain the omitted solver/warp states without concealing the HUD.
            d.rectangle((27,154,1325,179),fill=BG)
            text(d,(27,156),'Active flight shown. SAS holds attitude during solver searches + time warp.',19,MUTED)
        elif layout=='hook':
            text(d,(1418,225),'THREE FLY MODELS',29,TEAL,True)
            text(d,(1418,319),'The flies steer.',43,WHITE,True)
            text(d,(1418,416),'The flies set\nthe throttle.',43,WHITE,True)
            text(d,(1418,625),'Jeb / pitch\nBill / yaw\nBob / throttle',31,MUTED)
            text(d,(1418,831),'Around the Mun.\nBack to Kerbin.',33,TEAL,True)
            text(d,(1418,963),'A connectome model\nfor each control axis.',25,MUTED)
        elif layout=='landing':
            for y,value,label in [(250,'3 / 3','CREW HOME'),(475,'232 km','MUN FLYBY'),(700,'~34 min','ONE FLIGHT')]:
                text(d,(1440,y),value,67,TEAL,True);text(d,(1442,y+87),label,26,MUTED,True)
            text(d,(1440,959),'Parachute touchdown.\nNormal playback.',27,MUTED)
        else:
            text(d,(1418,185),'THREE FLY MODELS',29,TEAL,True)
            text(d,(1418,230),'Recorded neural activity',25,MUTED)
            for j,(name,role) in enumerate([('JEB','PITCH'),('BILL','YAW'),('BOB','THROTTLE')]):
                y=284+j*216
                d.rounded_rectangle((1418,y,1896,y+188),radius=14,fill='#101b2a',outline='#29394c',width=1)
                text(d,(1590,y+22),name,32,WHITE,True)
                text(d,(1590,y+64),role,24,TEAL,True)
                text(d,(1590,y+108),'Eye + optic\nlobe sample',22,MUTED)
            text(d,(1418,943),'Fly models: steering + throttle',25,TEAL)
            text(d,(1418,985),'Computer: guidance',25,MUTED)
    d.rectangle((24,1054,1896,1057),fill='#29394c')
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
    timeline=sum(s[1] for s in SHOTS[:i]);f += [f'[v]drawbox=x=24:y=1054:w={round(1872*(timeline+dur)/75)}:h=3:color=0x77e4ca:t=fill[out]']
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','4','-ss',str(start),'-t',str(dur*speed+.1),'-i',str(source),'-loop','1','-framerate','30','-i',str(base),'-filter_complex_threads','2','-filter_complex',';'.join(f),'-map','[out]','-an']
    if preview:cmd+=['-frames:v','1',str(out)]
    else:cmd+=['-frames:v',str(round(dur*30)),'-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-threads','4','-movflags','+faststart',str(out)]
    subprocess.run(cmd,check=True);print(f'{i+1}/{len(SHOTS)} {title.replace(chr(10)," ")}',flush=True)


def score():
    """Original martial percussion: layered low drums, toms, rolls and a quiet drone."""
    sr=48000;n=75*sr;rng=np.random.default_rng(731)
    dry=np.zeros((n,2),np.float32)
    def place(at,v,amp,pan=0):
        i=round(at*sr);N=min(len(v),n-i)
        if i<0 or N<=0:return
        dry[i:i+N,0]+=v[:N]*amp*math.sqrt((1-pan)/2)
        dry[i:i+N,1]+=v[:N]*amp*math.sqrt((1+pan)/2)
    def drum(at,amp=1,kind='low',pan=0):
        freq,decay,duration={'low':(51,3.2,2.3),'tom':(94,5.8,1.4),'high':(145,8.5,.9)}[kind]
        t=np.arange(round(duration*sr),dtype=np.float32)/sr
        # Falling pitch, inharmonic membrane modes, and a mallet transient.
        phase=2*np.pi*(freq*t+freq*.7*.028*(1-np.exp(-t/.028)))
        body=(np.sin(phase)+.29*np.sin(phase*1.59)+.12*np.sin(phase*2.14))*np.exp(-t*decay)
        noise=rng.normal(0,1,len(t)).astype(np.float32)
        noise=np.convolve(noise,np.ones(13,dtype=np.float32)/13,mode='same')
        attack=noise*np.exp(-t*44)*1.4
        v=(body+attack)*np.minimum(t/.002,1)
        place(at,v,amp,pan)
    beat=60/108
    # 108 BPM, halftime low drums with syncopated tom answers; escalating density.
    for bar in range(31):
        at=bar*4*beat
        if at>=67:break
        energy=.58 if at<3 else (.78 if at<20 else (.55 if at<35 else (.7 if at<51 else .95)))
        if at>=63:energy=.48
        for offset,level,kind,pan in [(0,1,'low',-.12),(1.5,.45,'tom',.32),(2,.83,'low',.12),(3,.5,'tom',-.35),(3.5,.3,'high',.4)]:
            when=at+offset*beat
            if when<67:drum(when+rng.uniform(0,.009),energy*level*rng.uniform(.95,1.05),kind,pan)
        if 10<=at<20 or 43<=at<63:
            for offset in [.75,2.75,3.75]:drum(at+offset*beat,.21*energy,'high',-.4 if offset<2 else .4)
        if bar%4==3 and at<63:
            for k in range(4):drum(at+(3+k/4)*beat,(.20+.08*k)*energy,'tom',(-1)**k*.35)
    # Sparse tonal floor supports the rhythm without a passive pad-led score.
    for at in np.arange(0,64,8):
        t=np.arange(10*sr,dtype=np.float32)/sr
        env=np.minimum(t/1.2,1)*np.minimum((10-t)/2,1)
        v=(np.sin(2*np.pi*82.407*t)+.28*np.sin(2*np.pi*123.471*t))*env
        place(at,v,.035)
    # Pull back for the final descent, then resolve as the capsule touches down.
    for at,amp in [(67,.40),(68.1,.24),(70.5,1.05),(71.05,.40)]:drum(at,amp,'low')
    for k in range(6):drum(70.05+k*.065,.11+k*.035,'tom',(-1)**k*.25)
    # A short room + long hall tail adds scale to the synthesized acoustic hits.
    audio=dry.copy()
    for delay,gain in [(.047,.12),(.091,.1),(.163,.075),(.277,.06),(.433,.05),(.681,.035),(.947,.025)]:
        shift=round(delay*sr);audio[shift:]+=dry[:-shift,::-1]*gain
    audio[:int(.025*sr)]*=np.linspace(0,1,int(.025*sr))[:,None]
    audio[-2*sr:]*=np.linspace(1,0,2*sr)[:,None]
    audio*=.85/max(np.max(np.abs(audio)),.01)
    path=WORK/'original-war-drums.wav'
    with wave.open(str(path),'wb') as w:
        w.setnchannels(2);w.setsampwidth(2);w.setframerate(sr);w.writeframes((audio*32767).astype('<i2').tobytes())
    return path


def main():
    p=argparse.ArgumentParser();p.add_argument('--preview',action='store_true');p.add_argument('--mux-only',action='store_true');p.add_argument('--shots',nargs='*',type=int);args=p.parse_args()
    WORK.mkdir(exist_ok=True,parents=True);OUT.mkdir(exist_ok=True,parents=True)
    source=next((ROOT/'video').glob('*.mov'))
    if not args.mux_only:
        for i in args.shots if args.shots is not None else range(len(SHOTS)):render(i,source,args.preview)
    if args.preview or args.shots is not None:return
    soundtrack=score()
    concat=WORK/'concat.txt';concat.write_text(''.join(f"file 'shot-{i:02}.mp4'\n" for i in range(len(SHOTS))))
    silent=OUT/'fly-ght-computer-16x9-v3-silent.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',str(silent)],check=True)
    final=OUT/'fly-ght-computer-16x9-v3.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(silent),'-i',str(soundtrack),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-af','loudnorm=I=-22:TP=-2:LRA=11','-t','75','-movflags','+faststart',str(final)],check=True)
    (OUT/'edit-decision-list.json').write_text(json.dumps({'source':str(source.relative_to(ROOT)),'duration':75,'resolution':[1920,1080],'audio':'Original synthesized war drums, 108 BPM, -22 LUFS target; source has no audio','sas':'Identical v2 SAS-off clip selections. HUD preserved. Final results card replaces SAS-on post-mission footage.','shots':[dict(zip(('source_start','duration','speed','title','subtitle','layout','gamma'),s)) for s in SHOTS]},indent=2))
    print(final,flush=True)

if __name__=='__main__':main()
