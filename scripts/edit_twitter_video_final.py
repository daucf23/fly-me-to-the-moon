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
 'Now the fly crew has to get everyone back to Kerbin.',
 'A return burn puts the capsule on course for entry.',
 'Re-entry pushes the crew to a peak of 4.5 G.',
 'Three fruit-fly connectome models, one very hot capsule.',
 'The parachutes open for the final descent.',
 'Touchdown: all three crew members are home.',
 '“Fly”-by-Wire takes three crew around the Mun and home.',
]
SHOTS=[(*s[:3],TITLES[i],'',*s[5:]) for i,s in enumerate(SOURCE_SHOTS)]

WORK = ROOT / 'video/edit-work/v5'
OUT = ROOT / 'video/exports/v5'


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
        for x,value,label in [(80,'3 / 3','CREW HOME'),(742,'232 km','MUN FLYBY'),(1350,'~34 min','ONE FLIGHT')]:
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
            for y,value,label in [(250,'3 / 3','CREW HOME'),(475,'232 km','MUN FLYBY'),(700,'~34 min','ONE FLIGHT')]:
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
    else:cmd+=['-frames:v',str(round(dur*30)),'-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-threads','4','-movflags','+faststart',str(out)]
    subprocess.run(cmd,check=True);print(f'{i+1}/{len(SHOTS)} {title.replace(chr(10)," ")}',flush=True)


def score():
    """One continuous musical clock, smoothly evolving arrangement, drum-only ending."""
    sr=48000;n=75*sr;rng=np.random.default_rng(20260912)
    dry=np.zeros((n,2),np.float32)
    def place(at,v,amp,pan=0):
        i=round(at*sr);N=min(len(v),n-i)
        if i<0 or N<=0:return
        dry[i:i+N,0]+=v[:N]*amp*math.sqrt((1-pan)/2)
        dry[i:i+N,1]+=v[:N]*amp*math.sqrt((1+pan)/2)
    def hz(m):return 440*2**((m-69)/12)
    def note(at,duration,m,amp,kind='pulse',pan=0):
        t=np.arange(round(duration*sr),dtype=np.float32)/sr;f=hz(m)
        v=np.zeros_like(t)
        if kind=='strings':
            for h in range(1,10):
                v+=(np.sin(2*np.pi*f*h*t+.003*h*np.sin(2*np.pi*5.2*t))+np.sin(2*np.pi*f*1.0018*h*t))/(h**1.55)
            env=np.sin(np.minimum(t/1.7,1)*np.pi/2)**2*np.sin(np.minimum((duration-t)/1.9,1)*np.pi/2)**2
            v*=env*(.87+.13*np.sin(2*np.pi*6.5*t))*.35
        else:
            for h in range(1,7):v+=np.sin(2*np.pi*f*h*t)*np.exp(-t*(5+h*1.1))/(h**1.5)
            v*=np.minimum(t/.009,1)*np.minimum((duration-t)/.05,1)
        place(at,v,amp,pan)
    def drum(at,amp=1,kind='low',pan=0):
        freq,decay,duration={'low':(49,3.4,2.1),'tom':(88,6,1.3),'high':(151,10,.8)}[kind]
        t=np.arange(round(duration*sr),dtype=np.float32)/sr
        phase=2*np.pi*(freq*t+freq*.62*.025*(1-np.exp(-t/.025)))
        body=(np.sin(phase)+.31*np.sin(phase*1.59)+.13*np.sin(phase*2.14))*np.exp(-t*decay)
        noise=rng.normal(0,1,len(t)).astype(np.float32)
        noise=np.convolve(noise,np.ones(9,dtype=np.float32)/9,mode='same')
        place(at,(body+noise*np.exp(-t*39)*1.3)*np.minimum(t/.002,1),amp,pan)
    def swell(at,duration,amp):
        t=np.arange(round(duration*sr),dtype=np.float32)/sr
        noise=rng.normal(0,1,len(t)).astype(np.float32)
        noise=np.convolve(noise,np.ones(27,dtype=np.float32)/27,mode='same')
        # Smooth rising texture in the score; not represented as game audio.
        env=(t/duration)**2*np.minimum((duration-t)/.08,1)
        phase=2*np.pi*(120*t+115*t*t/duration)
        place(at,(noise*.75+np.sin(phase)*.11)*env,amp,-.12)
    def smooth(at,points):
        times,values=zip(*points)
        j=int(np.searchsorted(times,at,side='right'))
        if j==0:return values[0]
        if j==len(times):return values[-1]
        q=(at-times[j-1])/(times[j]-times[j-1])
        q=(1-math.cos(math.pi*q))/2
        return values[j-1]+q*(values[j]-values[j-1])
    energy_points=[(0,.50),(3,.70),(16,.78),(23,.49),(29,.66),(38,.39),
                   (43,.54),(49,.79),(54,.94),(59,1.0),(62,.96),(67,.62),
                   (70,.58),(72.5,.70),(74,.64)]
    # Beat positions come from a single integral of smoothly changing BPM.
    # No scene boundary can reset the phase, pattern index or drum tail.
    clock=np.arange(0,75,.001)
    bpm=np.array([smooth(float(t),[(0,112),(40,112),(46,120),(52,128),(75,128)]) for t in clock])
    phase=np.cumsum(bpm/60)*.001;phase-=phase[0]
    quarter=np.arange(0,phase[-1],.25)
    times=np.interp(quarter,phase,clock)
    pattern=[64,59,64,66,67,64,71,66]
    events=[]
    for tick,at in enumerate(times):
        if at>73.65:break  # Leave space for the last drum's natural decay.
        at=float(at);beat=tick//4;part=tick%4
        energy=smooth(at,energy_points)
        tonal=smooth(at,[(0,1),(62,1),(65,.5),(68,0),(75,0)])
        if part==0:
            if beat%4 in (0,2):drum(at,energy*(1 if beat%4==0 else .76),'low',(-1)**beat*.08)
            if tonal>0:note(at,.56,40 if beat%8<6 else 47,energy*.14*tonal,'pulse')
        if part==2:
            drum(at,energy*.30,'tom',(-1)**beat*.32)
        if part==3:
            # Fine percussion grows continuously as the return becomes urgent.
            detail=smooth(at,[(0,.1),(38,.12),(48,.65),(54,1),(63,1),(68,.4),(75,.4)])
            drum(at,energy*.21*detail,'high',(-1)**beat*.42)
        if part in (0,2) and tonal>0:
            k=tick//2;m=pattern[k%8]
            high=smooth(at,[(0,0),(55,0),(60,1),(64,1),(68,0)])
            amp=energy*smooth(at,[(0,.10),(44,.10),(52,.14),(75,.14)])*tonal
            note(at,.42,m,amp*(1-.7*high),'pulse',(-1)**k*.35)
            if high>0:note(at,.42,m+12,amp*high*.78,'pulse',(-1)**k*.25)
        # Fills are musical phrases on the same grid, not attached to video cuts.
        if beat%16==15 and part in (1,3):
            drum(at,energy*(.22+.055*part),'tom',(-1)**part*.3)
        events.append({'time':round(at,6),'quarter_tick':tick,'bpm':round(float(np.interp(at,clock,bpm)),3)})
    # Overlapping sustained voicings carry harmony across the picture cuts.
    for at,duration,chord,amp in [(0,12,(52,55,59),.10),(10,13,(48,55,59),.12),
        (21,13,(52,59,66),.10),(32,13,(48,55,64),.095),
        (43,11,(50,57,64),.14),(51,10,(52,55,59,66),.17),
        (58,10,(54,59,64,67),.19)]:
        for j,m in enumerate(chord):note(at,duration,m,amp,'strings',(j-1)*.35)
    for at,duration,amp in [(14,5,.38),(25,5,.30),(42,6,.45),(48,5,.62),(58,5.5,.75)]:swell(at,duration,amp)
    # One shared room carries every voice and drum through every edit boundary.
    audio=dry.copy()
    for delay,gain in [(.047,.10),(.113,.08),(.227,.07),(.371,.06),(.613,.05),(.941,.035),(1.31,.02)]:
        shift=round(delay*sr);audio[shift:]+=dry[:-shift,::-1]*gain
    # Tonal voices finish before the end card; the beat continues through it.
    (WORK/'music-beat-map.json').write_text(json.dumps({'continuous_clock':True,'tempo':'112 to 128 BPM, smooth acceleration','end_card':'Drums only; no chord or beat reset','events':events},indent=2))
    audio[:round(.015*sr)]*=np.linspace(0,1,round(.015*sr))[:,None]
    audio[-round(.75*sr):]*=np.sin(np.linspace(np.pi/2,0,round(.75*sr)))[:,None]**2
    audio*=.85/max(np.max(np.abs(audio)),.01)
    # Gentle memoryless peak shaping preserves section dynamics without gain pumping.
    audio=.6*np.tanh(audio/.6)
    path=WORK/'original-continuous-mission.wav'
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
    silent=OUT/'fly-ght-computer-16x9-v5-silent.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',str(silent)],check=True)
    final=OUT/'fly-ght-computer-16x9-v5.mp4'
    # Measure once, then apply a single fixed gain to avoid dynamic gain pumping.
    measured=subprocess.run(['ffmpeg','-hide_banner','-i',str(soundtrack),'-af','loudnorm=I=-22:TP=-2:LRA=15:print_format=json','-f','null','-'],capture_output=True,text=True,check=True).stderr
    stats=json.JSONDecoder().raw_decode(measured[measured.rfind('{'):])[0]
    gain=min(-22-float(stats['input_i']),-2.2-float(stats['input_tp']))
    (OUT/'audio-mastering.json').write_text(json.dumps({'method':'Single constant gain across the entire soundtrack','gain_db':gain,'source_measurement':stats},indent=2))
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(silent),'-i',str(soundtrack),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-af',f'volume={gain:.6f}dB','-t','75','-movflags','+faststart',str(final)],check=True)
    (OUT/'edit-decision-list.json').write_text(json.dumps({'source':str(source.relative_to(ROOT)),'duration':75,'resolution':[1920,1080],'audio':'Original continuous mission score, smooth 112–128 BPM clock, overlapping harmonic voices, drum-only ending; constant-gain master; source has no audio','sas':'Identical v2 SAS-off clip selections. HUD preserved. Final results card replaces SAS-on post-mission footage.','shots':[dict(zip(('source_start','duration','speed','title','subtitle','layout','gamma'),s)) for s in SHOTS]},indent=2))
    print(final,flush=True)

if __name__=='__main__':main()
