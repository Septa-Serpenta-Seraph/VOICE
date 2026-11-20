import sys, os
sys.path.insert(0, '/home/adora/narusya-voice/analysis')
import numpy as np, soundfile as sf, parselmouth, librosa
from parselmouth.praat import call
from scipy.io import wavfile
from scipy.signal import lfilter
from scipy.ndimage import gaussian_filter1d
from frame_renderer import resonator_coeffs, lf_source_frame
import gate1_intelligibility as g1

SR = 48000; FRAME = 240
WORDS = ['heed','hid','head','had','hood','hud','hod','whod']
NAT = {w: f'/mnt/data/nar-r17/nat_{w}.wav' for w in WORDS}

def analyze(y, sr):
    snd = parselmouth.Sound(y, sr)
    pit = call(snd, "To Pitch", 0.005, 75, 500)
    times = pit.xs(); f0 = pit.selected_array['frequency']
    f0 = np.where(np.isfinite(f0) & (f0 > 0), f0, 0.0)
    form = call(snd, "To Formant (burg)", 0.005, 5, 5500, 0.025, 50)
    nf = form.get_number_of_frames()
    ft = np.array([form.get_time_from_frame_number(i+1) for i in range(nf)])
    F = np.zeros((nf,4)); BW = np.zeros((nf,4))
    for i in range(nf):
        t = ft[i]
        for k in range(4):
            try:
                fv = form.get_value_at_time(k+1, t); bw = form.get_bandwidth_at_time(k+1, t)
                F[i,k] = fv if (fv is not None and np.isfinite(fv)) else 0.0
                BW[i,k] = bw if (bw is not None and np.isfinite(bw) and bw > 0) else 100.0
            except Exception:
                F[i,k] = 0.0; BW[i,k] = 100.0
    return times, f0, ft, F, BW

def copy_synth(wav, out):
    y, sr = sf.read(wav); y = y.astype(np.float64)
    if y.ndim > 1: y = y.mean(1)
    if sr != SR: y = librosa.resample(y, orig_sr=sr, target_sr=SR); sr = SR
    times, f0, ft, F, BW = analyze(y, sr)
    n = len(y); t = np.arange(n)/sr
    f0_track = np.interp(t, times, f0)
    ftr = [np.interp(t, ft, F[:,k]) for k in range(4)]
    btr = [np.interp(t, ft, BW[:,k]) for k in range(4)]
    for k in range(4):
        last = 500*(k+1)
        for i in range(n):
            if ftr[k][i] <= 0: ftr[k][i] = last
            else: last = ftr[k][i]
    voiced = (f0_track > 0).astype(float)
    vmask = gaussian_filter1d(voiced, sigma=max(1, int(0.004*sr)))
    source = np.zeros(n); ps = {"pos_in_cycle":0.0}; rng = np.random.default_rng(42)
    for fs in range(0, n, FRAME):
        fe = min(fs+FRAME, n); fl = fe-fs; mid = fs+fl//2
        f0hz = max(75.0, min(600.0, f0_track[mid]))
        fr, ps = lf_source_frame(f0hz, 1.25, fl, ps, sr, 0.7, rng)
        source[fs:fe] = fr
    source = source * vmask
    output = np.zeros(n); state = {}
    for fs in range(0, n, FRAME):
        fe = min(fs+FRAME, n); fl = fe-fs
        if fl == 0: break
        mid = fs+fl//2
        for k in range(4):
            f_freq = ftr[k][mid]; bw = max(40.0, min(400.0, btr[k][mid]))
            if f_freq <= 0: continue
            b, a = resonator_coeffs(f_freq, bw, sr)
            zi = state.get(k, np.zeros(len(a)-1))
            o, zi_new = lfilter(b, a, source[fs:fe], zi=zi)
            state[k] = zi_new
            output[fs:fe] += o
    output = np.diff(output, prepend=output[0])
    output = output/(np.max(np.abs(output))+1e-12)*0.5
    wavfile.write(out, sr, (np.clip(output,-1,1)*32767).astype('int16'))
    return out

os.makedirs('/mnt/data/nar-copysynth', exist_ok=True)
nat_paths, cs_paths, targets = [], [], []
for w in WORDS:
    if not os.path.exists(NAT[w]):
        print(f'{w}: natural sample missing'); continue
    cs = copy_synth(NAT[w], f'/mnt/data/nar-copysynth/cs_{w}.wav')
    nat_paths.append(NAT[w]); cs_paths.append(cs); targets.append(w)

nat_h = g1.transcribe(nat_paths)
cs_h = g1.transcribe(cs_paths)
print(f"{'word':6s} {'natural->heard':24s} {'copysynth->heard':24s}")
nat_ok = cs_ok = 0
for w, nh, ch in zip(targets, nat_h, cs_h):
    nmatch = w.lower() in nh.lower(); cmatch = w.lower() in ch.lower()
    nat_ok += nmatch; cs_ok += cmatch
    print(f"{w:6s} {nh!r:24s} {ch!r:24s} {'NAT-OK' if nmatch else ''} {'CS-OK' if cmatch else ''}")
print(f"\nnatural oracle control: {nat_ok}/{len(targets)} | COPY-SYNTH through my plant: {cs_ok}/{len(targets)}")
