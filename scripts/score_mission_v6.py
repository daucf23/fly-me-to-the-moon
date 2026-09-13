"""Original continuous mission score performed with CC0 VSCO 2 CE recordings.

Samples: Sam Gossner & Simon Dalzell / Versilian Studios, CC0-1.0.
Exact source URLs and commit are in scripts/media/v6-samples.json.
Requires numpy and ffmpeg. No synthetic stand-in instruments.
"""
import json
import math
import re
import subprocess
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'video/edit-work/v6'
SR=48000
N=75*SR


def smooth(at,points):
    times,values=zip(*points);j=int(np.searchsorted(times,at,side='right'))
    if j==0:return values[0]
    if j==len(times):return values[-1]
    q=(1-math.cos(math.pi*(at-times[j-1])/(times[j]-times[j-1])))/2
    return values[j-1]+q*(values[j]-values[j-1])


def write_float(path,a):
    subprocess.run(['ffmpeg','-v','error','-y','-f','f32le','-ar',str(SR),'-ac','2','-i','pipe:0','-c:a','pcm_f32le',str(path)],input=np.asarray(a,dtype='<f4').tobytes(),check=True)


def score():
    manifest=json.loads((ROOT/'scripts/media/v6-samples.json').read_text())
    entries=manifest['samples'];cache={};rng=np.random.default_rng(640128)
    stems={k:np.zeros((N,2),np.float32) for k in ['percussion','ostinato','strings','cymbals']}
    def load(idx,ratio=1):
        key=(idx,round(ratio,7))
        if key in cache:return cache[key]
        entry=entries[idx];path=WORK/'samples'/entry['file']
        # Decode once, then resample with a band-limited high-precision converter.
        f=f'aresample=48000:resampler=swr:filter_size=64:phase_shift=12:cutoff=0.97,asetrate={round(SR*ratio)},aresample=48000:resampler=swr:filter_size=64:phase_shift=12:cutoff=0.97,highpass=f=28'
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-af',f,'-ac','2','-f','f32le','-'])
        a=np.frombuffer(raw,np.float32).reshape(-1,2).copy()
        peak=np.max(np.abs(a));a/=max(peak,.001)
        onset=np.flatnonzero(np.max(np.abs(a),axis=1)>.009)
        if len(onset):a=a[max(0,onset[0]-int(.004*SR)):]
        a[:min(96,len(a))]*=np.linspace(0,1,min(96,len(a)))[:,None]
        cache[key]=a;return a
    def add(stem,at,a,gain,pan=0,width=.7):
        i=round(at*SR);count=min(len(a),N-i)
        if count<=0 or i<0:return
        a=a[:count];mid=a.mean(axis=1);side=(a[:,0]-a[:,1])*.5*width
        v=np.column_stack((mid+side,mid-side))
        v[:,0]*=math.sqrt(1-pan);v[:,1]*=math.sqrt(1+pan)
        stems[stem][i:i+count]+=v*gain
    def tail(a,duration,fade=.15):
        a=a[:round(duration*SR)].copy();m=min(len(a),round(fade*SR))
        a[-m:]*=np.sin(np.linspace(np.pi/2,0,m))[:,None]**2
        return a
    def root_midi(entry):
        note=re.search(r'_([A-G]#?)([0-9])_',entry['source_path'])
        # VSCO's C3 = MIDI 60 (confirmed against the recorded fundamentals).
        names={'C':0,'C#':1,'D':2,'D#':3,'E':4,'F':5,'F#':6,'G':7,'G#':8,'A':9,'A#':10,'B':11}
        return (int(note[2])+2)*12+names[note[1]]
    def pitched(m,indices,rr=0):
        distances=[abs(root_midi(entries[j])-m) for j in indices]
        best=min(distances);candidates=[j for j,d in zip(indices,distances) if d==best]
        idx=candidates[rr%len(candidates)]
        return load(idx,2**((m-root_midi(entries[idx]))/12))
    def hit(at,energy,kind,rr):
        if kind=='bass':
            idx=(2 if energy>.8 else 0)+rr%2
            add('percussion',at,tail(load(idx),2.8,.5),energy*.52,width=.18)
        elif kind=='timp':
            # Keep the low tom-like voice in the score's E-minor tonal center.
            a=load(8+rr%2,82.407/89.5)
            add('percussion',at,tail(a,1.3,.45),energy*.17,(-1)**rr*.20,width=.5)
        elif kind=='snare':
            idx=4+(2 if energy>.75 else 0)+rr%2
            add('percussion',at,tail(load(idx),.85,.20),energy*.12,(-1)**rr*.15,width=.65)
    energy_points=[(0,.50),(3,.70),(16,.78),(23,.49),(29,.66),(38,.39),
                   (43,.54),(49,.79),(54,.94),(59,1.0),(62,.96),(67,.62),(70,.58),(72.5,.70),(74,.64)]
    clock=np.arange(0,75,.001)
    bpm=np.array([smooth(float(t),[(0,112),(40,112),(46,120),(52,128),(75,128)]) for t in clock])
    phase=np.cumsum(bpm/60)*.001;phase-=phase[0]
    grid=np.interp(np.arange(0,phase[-1],.25),phase,clock)
    pattern=[64,59,64,66,67,64,71,66];events=[]
    for tick,at in enumerate(grid):
        if at>73.15:break
        at=float(at);beat=tick//4;part=tick%4;energy=smooth(at,energy_points)
        tonal=smooth(at,[(0,1),(62,1),(65,.5),(68,0),(75,0)])
        jitter=float(rng.uniform(-.003,.003)) if at>.01 else 0
        if part==0:
            if beat%4 in (0,2):hit(at+jitter,energy*(1 if beat%4==0 else .76),'bass',beat)
            if tonal>0:
                a=pitched(40 if beat%8<6 else 47,range(12,26),beat)
                add('ostinato',at,tail(a,.64,.22),energy*.115*tonal,.08,width=.5)
        if part==2:hit(at+jitter,energy,'timp',beat)
        detail=smooth(at,[(0,.12),(38,.15),(48,.65),(54,1),(63,1),(68,.45),(75,.45)])
        if part==3:hit(at+jitter,energy*detail,'snare',beat)
        if beat%16==15 and part==1:hit(at+jitter,energy*.72,'snare',beat+1)
        if part in (0,2) and tonal>0:
            k=tick//2;m=pattern[k%8]
            high=smooth(at,[(0,0),(55,0),(60,1),(64,1),(68,0)])
            a=pitched(m,range(12,32),k)
            # Bow attacks retain their natural texture; releases overlap the pulse.
            add('ostinato',at+.006,tail(a,.58,.20),energy*.12*tonal*(1-.35*high),-.2,width=.8)
            if high>.01:
                a=pitched(m+12,range(26,32),k+1)
                add('ostinato',at+.010,tail(a,.53,.18),energy*.07*tonal*high,.24,width=.8)
        events.append({'time':round(at,6),'quarter_tick':tick})
    # Bowed phrases overlap; natural recordings replace the old additive pad.
    def sustain(at,duration,m,gain,pan):
        a=pitched(m,range(32,37));target=round(duration*SR)
        # Crossfade the middle of the recorded sustain if a phrase exceeds its length.
        result=a.copy()
        while len(result)<target:
            chunk=a[round(.8*SR):].copy();overlap=min(round(1.5*SR),len(chunk)//3)
            ramp=np.linspace(0,1,overlap)[:,None]
            result[-overlap:]=result[-overlap:]*(1-ramp)+chunk[:overlap]*ramp
            result=np.concatenate((result,chunk[overlap:]))
        result=result[:target].copy();attack=min(round(1.5*SR),target//3);release=min(round(2*SR),target//3)
        result[:attack]*=np.sin(np.linspace(0,np.pi/2,attack))[:,None]**2
        result[-release:]*=np.sin(np.linspace(np.pi/2,0,release))[:,None]**2
        add('strings',at,result,gain,pan,.8)
    for at,duration,chord,gain in [(0,12,(52,55,59),.055),(10,13,(48,55,59),.06),
        (21,13,(52,59,66),.052),(32,13,(48,55,64),.047),
        (43,11,(50,57,64),.07),(51,10,(52,55,59,66),.079),(58,10,(54,59,64,67),.085)]:
        for j,m in enumerate(chord):sustain(at,duration,m,gain,(j-1.5)*.19)
    # Recorded suspended cymbal crescendos instead of pitched synthetic risers.
    cym=load(37)
    for at,duration,gain in [(14,5,.028),(25,5,.021),(42,6,.035),(48,5,.038),(58,5.5,.05)]:
        count=round(duration*SR);a=cym[:count].copy()
        a*=np.sin(np.linspace(0,np.pi,len(a)))[:,None]**2
        add('cymbals',at,a,gain,.07,.95)
    # A compact diffuse room: low wet level, no discrete repeated echoes.
    audio=sum(stems.values());mono=(stems['ostinato']+stems['strings']+stems['percussion']*.32).mean(axis=1)
    irn=round(1.25*SR);t=np.arange(irn)/SR;pre=round(.022*SR)
    size=1<<(len(mono)+irn-2).bit_length();spectrum=np.fft.rfft(mono,size)
    for ch in range(2):
        ir=rng.normal(size=irn)*np.exp(-t*6.0)
        ir[:pre]=0;ir[pre:pre+480]*=np.linspace(0,1,480)
        ir=np.convolve(ir,np.ones(5)/5,mode='same');ir/=max(np.sqrt(np.sum(ir**2)),1e-9)
        wet=np.fft.irfft(spectrum*np.fft.rfft(ir,size),size)[:N]
        audio[:,ch]+=wet.astype(np.float32)*.085
    audio[:480]*=np.linspace(0,1,480)[:,None]
    audio[-round(.8*SR):]*=np.sin(np.linspace(np.pi/2,0,round(.8*SR)))[:,None]**2
    audio*=.85/max(float(np.max(np.abs(audio))),.01)
    # Very gentle static peak shaping, no scene-triggered compressor or gain changes.
    audio=.65*np.tanh(audio/.65)
    path=WORK/'orchestral-mix-float.wav';write_float(path,audio)
    (WORK/'music-beat-map.json').write_text(json.dumps({'continuous_clock':True,'ending':'Recorded drums only, no closing chord','events':events},indent=2))
    return path
