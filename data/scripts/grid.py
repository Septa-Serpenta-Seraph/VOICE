#!/usr/bin/env python3
"""Round 17 — /i/ F1 rescue grid. Narusya's clone (/mnt/data/nar-r17/voice).

Judged on golden WER via the independent faster-whisper-base oracle (gate1),
NOT on acoustic lift. Acoustic probes use Zarza's r17_pointer.py method
(sustained via frame_renderer, word-middle via render_plan_v3, welch peaks
in +/-15% target windows) so numbers are comparable with her pointer.

Usage: PYTHONPATH= /mnt/data/pocket-tts-venv/bin/python grid.py <config>
One config per run; appends /mnt/data/nar-r17/results.json.
"""
import sys, os, json, time
V = '/mnt/data/nar-r17/voice'
sys.path.insert(0, V + '/analysis')
import numpy as np, yaml
from scipy.signal import welch
from scipy.io import wavfile
from render_plan import build_plan, Style, SR, RenderPlan, Segment
import prosody_poststage as pp
import frame_renderer as fr
import gate1_intelligibility as g1

EXP = '/mnt/data/nar-r17'
WAVS = EXP + '/wavs'
os.makedirs(WAVS, exist_ok=True)
genome = yaml.safe_load(open(V + '/genome/voice_genome.yaml'))
grid = genome['vowel_grid']
WORDS = ['see', 'me', 'she', 'sit', 'set', 'moon']

CONFIGS = {
    'base':       dict(gain=1.0),
    'g2':         dict(gain=2.0),
    'g4':         dict(gain=4.0),
    'g8':         dict(gain=8.0),
    'g16':        dict(gain=16.0),
    'g24':        dict(gain=24.0),
    'g16lo':      dict(gain=16.0, max_hz=500.0),
    'g24lo':      dict(gain=24.0, max_hz=500.0),
    'g8bw100':    dict(gain=8.0, bw=100.0),
    'g8bw120':    dict(gain=8.0, bw=120.0),
    'g16bw100':   dict(gain=16.0, bw=100.0),
    'g16bw120':   dict(gain=16.0, bw=120.0),
    'g16lobw120': dict(gain=16.0, max_hz=500.0, bw=120.0),
    'g24lobw120': dict(gain=24.0, max_hz=500.0, bw=120.0),
}

def set_hooks(cfg):
    for mod in (pp, fr):
        mod._R17_F1_GAIN = cfg.get('gain', 1.0)
        mod._R17_F1_GAIN_MAX_HZ = cfg.get('max_hz')
        mod._R17_BW_OVERRIDE = {'F1': cfg['bw']} if cfg.get('bw') else None

def sustained_rel(vp='i'):
    """Zarza's method: 1s bare vowel via frame_renderer, welch 0.3-0.8s."""
    g = grid[vp]
    seg = Segment(i=0, phone=vp, kind='vowel', t0=0.0, t1=1.0, word=0, syll=0,
                  stress=1, voiced=True,
                  targets={'F1': g[0], 'F2': g[1], 'F3': g[2], 'F4': 3100})
    y = fr.render_plan(RenderPlan(text=vp, words=[vp], segments=[seg],
                                  style=Style(seed=42)), genome)
    f, P = welch(y[int(0.3*SR):int(0.8*SR)], fs=SR, nperseg=8192)
    pk = []
    for tgt in g[:3]:
        m = (f >= tgt*0.85) & (f <= tgt*1.15)
        pk.append(float(10*np.log10(P[m].max()+1e-20)) if m.any() else None)
    return [round(p - pk[0], 1) for p in pk]

def word_i_rel(word):
    """Zarza's method: middle 40% of the /i/ segment, welch 4096."""
    pl = build_plan(word, style=Style(seed=42))
    a = pp.render_plan_v3(pl, genome)
    for seg in pl.segments:
        if seg.kind == 'vowel' and seg.phone == 'i':
            t0, t1 = seg.t0, seg.t1
            y = a[int((t0+0.3*(t1-t0))*SR):int((t1-0.3*(t1-t0))*SR)]
            f, P = welch(y, fs=SR, nperseg=4096)
            pk = []
            for tgt in grid['i'][:3]:
                m = (f >= tgt*0.85) & (f <= tgt*1.15)
                pk.append(float(10*np.log10(P[m].max()+1e-20)) if m.any() else None)
            return [round(p - pk[0], 1) for p in pk]
    return None

def cons_vowel_db(word):
    """RMS of consonant segments vs vowel segments in the rendered word.
    Tests the normalization-crush hypothesis: big F1 gain raises the vowel
    peak, peak-normalize then scales the consonant branch down with it."""
    pl = build_plan(word, style=Style(seed=42))
    a = pp.render_plan_v3(pl, genome)
    cr, vr = [], []
    for seg in pl.segments:
        t0, t1 = int(seg.t0*SR), min(int(seg.t1*SR), len(a))
        if t1 <= t0:
            continue
        rms = float(np.sqrt(np.mean(a[t0:t1]**2)))
        if seg.kind in ('vowel', 'diphthong'):
            vr.append(rms)
        elif seg.kind != 'silence':
            cr.append(rms)
    if not cr or not vr or max(vr) <= 0:
        return None
    return round(20*np.log10((sum(cr)/len(cr)) / (sum(vr)/len(vr))), 1)

def run(name):
    cfg = CONFIGS[name]
    set_hooks(cfg)
    t_start = time.time()
    paths, targets = [], []
    for i, t in enumerate(g1.GOLDEN):
        a = pp.render_plan_v3(build_plan(t, style=Style(seed=42)), genome)
        p = f'{WAVS}/{name}_g{i}.wav'
        wavfile.write(p, SR, (np.clip(a, -1, 1)*32767).astype('int16'))
        paths.append(p); targets.append(t)
    for i, w in enumerate(WORDS):
        a = pp.render_plan_v3(build_plan(w, style=Style(seed=42)), genome)
        p = f'{WAVS}/{name}_w{i}.wav'
        wavfile.write(p, SR, (np.clip(a, -1, 1)*32767).astype('int16'))
        paths.append(p); targets.append(w)
    hyps = g1.transcribe(paths)
    gW = [g1.word_error(t, x) for t, x in zip(targets[:4], hyps[:4])]
    wW = [g1.word_error(t, x) for t, x in zip(targets[4:], hyps[4:])]
    rec = {
        'name': name, 'cfg': cfg,
        'golden_wer': [round(float(x), 3) for x in gW],
        'golden_mean': round(float(np.mean(gW)), 3),
        'golden_pass': sum(1 for x in gW if x <= 0.34),
        'word_mean': round(float(np.mean(wW)), 3),
        'word_exact': sum(1 for t, x in zip(WORDS, hyps[4:])
                          if t.lower() in x.lower().split() or x.lower().strip(' .!') == t),
        'heard_golden': hyps[:4], 'heard_words': hyps[4:],
        'sustained_i_rel': sustained_rel('i'),
        'i_rel_me': word_i_rel('me'), 'i_rel_see': word_i_rel('see'),
        'cons_vowel_db_see': cons_vowel_db('see'),
        'cons_vowel_db_moon': cons_vowel_db('moon'),
        'render_s': round(time.time() - t_start, 1),
    }
    rp = EXP + '/results.json'
    results = json.load(open(rp)) if os.path.exists(rp) else []
    results = [r for r in results if r['name'] != name] + [rec]
    json.dump(results, open(rp, 'w'), indent=1)
    print(json.dumps(rec, indent=1))
    print(f'SAVED {rp} ({len(results)} configs)')

if __name__ == '__main__':
    run(sys.argv[1])
