#!/usr/bin/env python3
"""Round 18 — vowel envelope + aperiodic fill, judged on HELD-OUT.

Zarza's r18 diagnosis: golden 2/4 is a narrow island (Whisper LM rescues
canonical phrases). Sustained envelopes on shipped tree 791ce3a:
  /i/  [0, +54.4, +51.6]  F1 starved        <- broken
  /ɪ/  [0, -15.1, -15.5]  F1 over-dominant  <- broken
  /ɛ/  [0, -2.5, -7.0]    ~natural
  /ɑ/  [0, -3.6, -15.4]   ~natural
  /u/  [0, -6.7, -20.7]   ~natural (island vowel, protect)

Levers: per-vowel formant envelope gains (nearest-grid-vowel labeling),
per-vowel F1 bandwidth, aspiration fill (fr._aspiration_level.cached).
Eval: golden 4 (regression, keep >=2/4) + Zarza held-out 8 + Nar held-out 5
+ /i/ word probe 10. Primary judge: novel-sentence WER, not the gate set.

Usage: PYTHONPATH= /mnt/data/pocket-tts-venv/bin/python grid3.py <config>
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

ZARZA_HO = [
    "We see the sea.",
    "The cat sat on the mat.",
    "Three green trees.",
    "Who took the book?",
    "The strong spring brings bright blooms.",
    "Six thick thistles twist.",
    "A small green frog sat on the old wooden log by the pond.",
    "The quick student asked several strange questions after class.",
]
MY_HO = [
    "She sells sea shells.",
    "I see the green tree.",
    "The sun is bright today.",
    "We like the moonlight.",
    "He sees you.",
]
IWORDS = ["see", "me", "she", "we", "he", "key", "free", "three", "sit", "set"]

ENV_MILD = {'i': {'F1': 4.0, 'F3': 0.5},
            '\u026a': {'F1': 0.7, 'F2': 2.0, 'F3': 2.0}}
ENV_STRONG = {'i': {'F1': 8.0, 'F3': 0.25},
              '\u026a': {'F1': 0.7, 'F2': 2.0, 'F3': 2.0}}

CONFIGS = {
    'base':      dict(),
    'asp20':     dict(asp=-20.0),
    'asp30':     dict(asp=-30.0),
    'env_mild':  dict(env=ENV_MILD),
    'env_strong': dict(env=ENV_STRONG),
    'bw_i_160':  dict(env={'i': {'F3': 0.5}}, bwv={'i': {'F1': 160.0}}),
    'bw_i_200':  dict(env={'i': {'F3': 0.5}}, bwv={'i': {'F1': 200.0}}),
    'env_mild_asp30': dict(env=ENV_MILD, asp=-30.0),
    'env_strong_asp30': dict(env=ENV_STRONG, asp=-30.0),
    'bw_i_160_asp30': dict(env={'i': {'F3': 0.5}}, bwv={'i': {'F1': 160.0}}, asp=-30.0),
}

def set_hooks(cfg):
    for mod in (pp, fr):
        mod._R18_ENVELOPE = cfg.get('env')
        mod._R18_BW_VOWEL = cfg.get('bwv')
    if cfg.get('asp') is not None:
        fr._aspiration_level.cached = float(cfg['asp'])
    else:
        fr._aspiration_level.cached = None  # re-read genome (-120 = OFF)

def sustained_rel(vp):
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
    flat = float(np.exp(np.mean(np.log(P[(f>=100)&(f<=8000)]+1e-20))) /
                 (np.mean(P[(f>=100)&(f<=8000)])+1e-20))
    return [round(p - pk[0], 1) for p in pk], round(flat, 4)

def word_i_rel(word):
    pl = build_plan(word, style=Style(seed=42))
    a = pp.render_plan_v3(pl, genome)
    for seg in pl.segments:
        if seg.kind == 'vowel' and seg.phone == 'i':
            t0, t1 = seg.t0, seg.t1
            y = a[int((t0+0.3*(t1-t0))*SR):int((t1-0.3*(t1-t0))*SR)]
            if len(y) < 512:
                return None
            f, P = welch(y, fs=SR, nperseg=min(4096, len(y)))
            pk = []
            for tgt in grid['i'][:3]:
                m = (f >= tgt*0.85) & (f <= tgt*1.15)
                pk.append(float(10*np.log10(P[m].max()+1e-20)) if m.any() else None)
            return [round(p - pk[0], 1) for p in pk]
    return None

def render_set(texts, name, tag):
    paths = []
    for i, t in enumerate(texts):
        a = pp.render_plan_v3(build_plan(t, style=Style(seed=42)), genome)
        p = f'{WAVS}/{name}_{tag}{i}.wav'
        wavfile.write(p, SR, (np.clip(a, -1, 1) * 32767).astype('int16'))
        paths.append(p)
    return paths

def run(name):
    cfg = CONFIGS[name]
    set_hooks(cfg)
    t_start = time.time()
    gp = render_set(g1.GOLDEN, name, 'g')
    zp = render_set(ZARZA_HO, name, 'z')
    mp = render_set(MY_HO, name, 'm')
    wp = render_set(IWORDS, name, 'w')
    hyps = g1.transcribe(gp + zp + mp + wp)
    ng, nz, nm = len(g1.GOLDEN), len(ZARZA_HO), len(MY_HO)
    gW = [g1.word_error(t, x) for t, x in zip(g1.GOLDEN, hyps[:ng])]
    zW = [g1.word_error(t, x) for t, x in zip(ZARZA_HO, hyps[ng:ng+nz])]
    mW = [g1.word_error(t, x) for t, x in zip(MY_HO, hyps[ng+nz:ng+nz+nm])]
    wH = hyps[ng+nz+nm:]
    w_exact = sum(1 for t, x in zip(IWORDS, wH)
                  if x.lower().strip(' .!?') == t or t in x.lower().split())
    si, fi = sustained_rel('i')
    su, fu = sustained_rel('u')
    sji, fji = sustained_rel('\u026a')
    rec = {
        'name': name, 'cfg': {k: v for k, v in cfg.items()},
        'golden_wer': [round(float(x), 3) for x in gW],
        'golden_mean': round(float(np.mean(gW)), 3),
        'golden_pass': sum(1 for x in gW if x <= 0.34),
        'heard_golden': hyps[:ng],
        'zarza_ho_mean': round(float(np.mean(zW)), 3),
        'zarza_ho_pass': sum(1 for x in zW if x <= 0.34),
        'zarza_ho_wer': [round(float(x), 3) for x in zW],
        'heard_zarza_ho': hyps[ng:ng+nz],
        'my_ho_mean': round(float(np.mean(mW)), 3),
        'my_ho_pass': sum(1 for x in mW if x <= 0.34),
        'heard_my_ho': hyps[ng+nz:ng+nz+nm],
        'iwords_exact': w_exact, 'heard_iwords': wH,
        'sustained_i': si, 'flat_i': fi,
        'sustained_u': su, 'flat_u': fu,
        'sustained_ji': sji, 'flat_ji': fji,
        'i_rel_me': word_i_rel('me'),
        'render_s': round(time.time() - t_start, 1),
    }
    rp = EXP + '/results3.json'
    results = json.load(open(rp)) if os.path.exists(rp) else []
    results = [r for r in results if r['name'] != name] + [rec]
    json.dump(results, open(rp, 'w'), indent=1)
    print(json.dumps(rec, indent=1))
    print(f'SAVED {rp} ({len(results)} configs)')

if __name__ == '__main__':
    run(sys.argv[1])
