#!/usr/bin/env python3
"""Round 17b — steady-state duration levers. Narusya's clone.

Reproduces Zarza's two proofs (slow100, shorttrans CV25/VC20), then tests
the proportional transition budget (prop). Every config also renders a
HELD-OUT set (not in golden, not in Zarza's sets) — the discipline she asked
for. Judged on WER via the independent faster-whisper-base oracle.

Usage: PYTHONPATH= /mnt/data/pocket-tts-venv/bin/python grid2.py <config>
"""
import sys, os, json, time
import grid  # loads clone paths, genome, measurement helpers
import numpy as np
from scipy.io import wavfile
from render_plan import build_plan, Style, SR
import prosody_poststage as pp
import time_varying as tv
import gate1_intelligibility as g1

EXP = '/mnt/data/nar-r17'
WAVS = EXP + '/wavs'
genome = grid.genome
WORDS = grid.WORDS
HELDOUT = [
    "She sells sea shells.",
    "I see the green tree.",
    "The sun is bright today.",
    "We like the moonlight.",
    "He sees you.",
]

CONFIGS = {
    'base':       dict(),
    'slow100':    dict(rate=100.0),
    'shorttrans': dict(cv_ms=25, vc_ms=20),
    'prop':       dict(prop=True),
    'prop_g4':    dict(prop=True, gain=4.0),
    'prop_g8':    dict(prop=True, gain=8.0),
    'prop_g16lo': dict(prop=True, gain=16.0, max_hz=500.0),
}

def set_hooks(cfg):
    grid.set_hooks(cfg)
    tv._R17_CV_MS = cfg.get('cv_ms')
    tv._R17_VC_MS = cfg.get('vc_ms')
    tv._R17_PROP_TRANS = bool(cfg.get('prop'))

def written_ms(req_ms):
    """Producer contract: round(ms/10) glide frames + 1 steady, 10ms each."""
    return (round(req_ms / 10) + 1) * 10

def steady_audit(pl, cfg):
    segs = sorted([s for s in pl.segments if s.kind != 'silence'],
                  key=lambda s: s.t0)
    out = []
    for j, s in enumerate(segs):
        if s.kind not in ('vowel', 'diphthong'):
            continue
        D = (s.t1 - s.t0) * 1000
        prev_c = j > 0 and segs[j-1].kind not in ('vowel', 'diphthong')
        next_c = j < len(segs)-1 and segs[j+1].kind not in ('vowel', 'diphthong')
        if cfg.get('prop'):
            cv = tv.prop_written_ms(D, 60) if prev_c else 0
            vc = tv.prop_written_ms(D, 50) if next_c else 0
        else:
            cv = written_ms(cfg.get('cv_ms', 50)) if prev_c else 0
            vc = written_ms(cfg.get('vc_ms', 40)) if next_c else 0
        out.append([s.phone, round(D), round(D - cv - vc)])
    return out

def render_set(texts, name, tag, cfg):
    paths = []
    rate = cfg.get('rate', 142.5)
    audits = []
    for i, t in enumerate(texts):
        pl = build_plan(t, style=Style(seed=42, rate_wpm=rate))
        a = pp.render_plan_v3(pl, genome)
        p = f'{WAVS}/{name}_{tag}{i}.wav'
        wavfile.write(p, SR, (np.clip(a, -1, 1) * 32767).astype('int16'))
        paths.append(p)
        audits.append(steady_audit(pl, cfg))
    return paths, audits

def run(name):
    cfg = CONFIGS[name]
    set_hooks(cfg)
    t_start = time.time()
    gp, ga = render_set(g1.GOLDEN, name, 'g', cfg)
    wp, _ = render_set(WORDS, name, 'w', cfg)
    hp, ha = render_set(HELDOUT, name, 'h', cfg)
    hyps = g1.transcribe(gp + wp + hp)
    n_g, n_w = len(g1.GOLDEN), len(WORDS)
    gW = [g1.word_error(t, x) for t, x in zip(g1.GOLDEN, hyps[:n_g])]
    wW = [g1.word_error(t, x) for t, x in zip(WORDS, hyps[n_g:n_g+n_w])]
    hW = [g1.word_error(t, x) for t, x in zip(HELDOUT, hyps[n_g+n_w:])]
    minsteady = min((s[2] / s[1] for a in ga + ha for s in a if s[1] > 0), default=1.0)
    rec = {
        'name': name, 'cfg': cfg,
        'golden_wer': [round(float(x), 3) for x in gW],
        'golden_mean': round(float(np.mean(gW)), 3),
        'golden_pass': sum(1 for x in gW if x <= 0.34),
        'heard_golden': hyps[:n_g],
        'word_mean': round(float(np.mean(wW)), 3),
        'heard_words': hyps[n_g:n_g+n_w],
        'ho_wer': [round(float(x), 3) for x in hW],
        'ho_mean': round(float(np.mean(hW)), 3),
        'ho_pass': sum(1 for x in hW if x <= 0.34),
        'heard_ho': hyps[n_g+n_w:],
        'min_steady_frac': round(float(minsteady), 3),
        'vowel_audit_moon': ga[0], 'vowel_audit_sun': ga[1],
        'render_s': round(time.time() - t_start, 1),
    }
    rp = EXP + '/results2.json'
    results = json.load(open(rp)) if os.path.exists(rp) else []
    results = [r for r in results if r['name'] != name] + [rec]
    json.dump(results, open(rp, 'w'), indent=1)
    print(json.dumps(rec, indent=1))
    print(f'SAVED {rp} ({len(results)} configs)')

if __name__ == '__main__':
    run(sys.argv[1])
