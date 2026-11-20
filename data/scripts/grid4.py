#!/usr/bin/env python3
"""Round 19 — isolated-vowel assay + high-formant (F2/F3) bandwidth/salience.

Zarza's r19 wall: the vowel itself, no onset, is unrecognizable. /u/->"You"
passes; /i/,/ɑ/,/ɛ/ -> "" fail. /i/ F2 band (1800-2800) is only ~4 dB over
/u/'s, so the high-F2 front-vowel cue never resolves; /i/ collapses to /u/.
whisper-small fails the same words -> it is the voice, not the oracle.

Physics: at F0~190 harmonics are 190 Hz apart. F2=2350 sits BETWEEN H12=2280
and H13=2470; the narrow bw100 resonator builds two skirt-excited harmonic
lines, not a broad formant peak. The mel frontend reads a harmonic stack, not
a front-vowel formant. Widening F2/F3 (NOT F1 -> Shhh smear) spans multiple
harmonics -> broad damped formant peak + faster pitch-synchronous decay.

NEW FLOOR: isolated-vowel assay (each vowel alone, 250 ms, render_plan_v3,
whisper-base). Phoneme-level judge via vendored CMUdict g2p: heard word's
vowel must match the target's front/back+height category. /i/->"You"(/u/) FAILS.
Then golden regression (protect the island) for any winner.

Usage: PYTHONPATH= /mnt/data/pocket-tts-venv/bin/python grid4.py <config>
"""
import sys, os, json, time, re
V = '/mnt/data/nar-r17/voice'
sys.path.insert(0, V + '/analysis')
import numpy as np, yaml
from scipy.signal import welch
from scipy.io import wavfile
from render_plan import build_plan, Style, SR, RenderPlan, Segment
import prosody_poststage as pp
import frame_renderer as fr
import gate1_intelligibility as g1
from lexicon import g2p_word, _is_vowel_ipa

EXP = '/mnt/data/nar-r17'
WAVS = EXP + '/wavs'
os.makedirs(WAVS, exist_ok=True)
genome = yaml.safe_load(open(V + '/genome/voice_genome.yaml'))
grid = genome['vowel_grid']
VOWELS = ['i', '\u026a', 'e', '\u025b', '\u00e6', '\u0251', '\u028c',
          '\u0254', 'o', '\u028a', 'u', '\u0259']

# front/back + height category sets. The collapse mode is front->back, so
# /i/ accepts only front-high vowels, never u/ʊ.
CAT = {
    'i': {'i', '\u026a'}, '\u026a': {'\u026a', 'i'},
    'e': {'e', '\u025b'}, '\u025b': {'\u025b', 'e'},
    '\u00e6': {'\u00e6', 'a', '\u025b'},
    '\u0251': {'\u0251', '\u0254', 'a'},
    '\u028c': {'\u028c', '\u0259', '\u0251'},
    '\u0254': {'\u0254', 'o', '\u0251'}, 'o': {'o', '\u0254'},
    '\u028a': {'\u028a', 'u'}, 'u': {'u', '\u028a'},
    '\u0259': {'\u0259', '\u028c'},
}
LETTER_V = {'a': 'e', 'b': 'i', 'c': 'i', 'd': 'i', 'e': 'i', 'f': '\u025b',
            'g': 'i', 'h': 'e', 'i': 'a', 'j': 'e', 'k': 'e', 'l': '\u025b',
            'm': '\u025b', 'n': '\u025b', 'o': 'o', 'p': 'i', 'q': 'u',
            'r': '\u0251', 's': '\u025b', 't': 'i', 'u': 'u', 'v': 'i',
            'w': '\u028c', 'x': '\u025b', 'y': 'a', 'z': 'i'}

CONFIGS = {
    'base':         dict(),
    'hf200':        dict(highbw={'F2': 200.0, 'F3': 200.0}),
    'hf300':        dict(highbw={'F2': 300.0, 'F3': 300.0}),
    'hf400':        dict(highbw={'F2': 400.0, 'F3': 400.0}),
    'hf500':        dict(highbw={'F2': 500.0, 'F3': 500.0}),
    'f2only300':    dict(highbw={'F2': 300.0}),
    'f2_300_f3_200': dict(highbw={'F2': 300.0, 'F3': 200.0}),
    'f2_400_f3_300': dict(highbw={'F2': 400.0, 'F3': 300.0}),
    'asp14':        dict(asp=-14.0),
    'asp20':        dict(asp=-20.0),
    'asp30':        dict(asp=-30.0),
    'asp20_hf300':  dict(asp=-20.0, highbw={'F2': 300.0, 'F3': 300.0}),
    'bright10':     dict(bright=10.0),
    'bright20':     dict(bright=20.0),
}

def set_hooks(cfg):
    for mod in (pp, fr):
        mod._R18_ENVELOPE = None
        mod._R18_BW_VOWEL = None
        mod._R19_HIGHBW = cfg.get('highbw')
    pp._R19_BRIGHT_DB = cfg.get('bright')
    fr._aspiration_level.cached = float(cfg['asp']) if cfg.get('asp') is not None else None

def heard_vowels(heard):
    """Vowel phones present in the heard transcription (g2p + letter fallback)."""
    vs = set()
    for tok in re.findall(r"[a-z]+", heard.lower()):
        if len(tok) == 1 and tok in LETTER_V:
            vs.add(LETTER_V[tok]); continue
        try:
            phones, _, _ = g2p_word(tok)
        except Exception:
            continue
        for ph in phones:
            if _is_vowel_ipa(ph):
                vs.add(ph)
            else:
                for ch in ph:           # diphthong components
                    if ch in 'i\u026ae\u025b\u00e6\u0251\u028c\u0254o\u028au\u0259':
                        vs.add(ch)
    return vs

def iso_pass(vp, heard):
    if not heard.strip():
        return False, set()
    vs = heard_vowels(heard)
    return bool(vs & CAT[vp]), vs

def render_iso(vp, name):
    g = grid[vp]
    seg = Segment(i=0, phone=vp, kind='vowel', t0=0.0, t1=0.25, word=0, syll=0,
                  stress=1, voiced=True,
                  targets={'F1': g[0], 'F2': g[1], 'F3': g[2], 'F4': 3100})
    plan = RenderPlan(text=vp, words=[vp], segments=[seg], style=Style(seed=42))
    a = pp.render_plan_v3(plan, genome)
    p = f'{WAVS}/{name}_iso_{vp}.wav'
    wavfile.write(p, SR, (np.clip(a, -1, 1) * 32767).astype('int16'))
    return p, a

def band_db(a, lo, hi):
    f, P = welch(a, fs=SR, nperseg=4096)
    m = (f >= lo) & (f <= hi)
    return round(float(10 * np.log10(P[m].sum() + 1e-20)), 1) if m.any() else None

def run(name):
    cfg = CONFIGS[name]
    set_hooks(cfg)
    t0 = time.time()
    iso_paths, iso_audio = [], {}
    for vp in VOWELS:
        p, a = render_iso(vp, name)
        iso_paths.append(p); iso_audio[vp] = a
    gp = []
    for i, t in enumerate(g1.GOLDEN):
        a = pp.render_plan_v3(build_plan(t, style=Style(seed=42)), genome)
        p = f'{WAVS}/{name}_g{i}.wav'
        wavfile.write(p, SR, (np.clip(a, -1, 1) * 32767).astype('int16'))
        gp.append(p)
    hyps = g1.transcribe(iso_paths + gp)
    iso_h = hyps[:len(VOWELS)]; g_h = hyps[len(VOWELS):]
    iso_res = {}
    npass = 0
    for vp, h in zip(VOWELS, iso_h):
        ok, vs = iso_pass(vp, h)
        npass += ok
        iso_res[vp] = {'heard': h, 'pass': ok, 'heard_vowels': sorted(vs)}
    gW = [g1.word_error(t, x) for t, x in zip(g1.GOLDEN, g_h)]
    ai = iso_audio['i']; au = iso_audio['u']
    rec = {
        'name': name, 'cfg': cfg,
        'iso_pass': npass, 'iso_total': len(VOWELS),
        'iso_i_pass': iso_res['i']['pass'], 'iso_i_heard': iso_res['i']['heard'],
        'iso_u_pass': iso_res['u']['pass'], 'iso_u_heard': iso_res['u']['heard'],
        'isolated': iso_res,
        'golden_mean': round(float(np.mean(gW)), 3),
        'golden_pass': sum(1 for x in gW if x <= 0.34),
        'golden_wer': [round(float(x), 3) for x in gW],
        'heard_golden': g_h,
        'i_F2band': band_db(ai, 1800, 2800), 'i_F3band': band_db(ai, 2800, 3800),
        'u_F2band': band_db(au, 1800, 2800),
        'i_minus_u_F2band': round(band_db(ai, 1800, 2800) - band_db(au, 1800, 2800), 1),
        'render_s': round(time.time() - t0, 1),
    }
    rp = EXP + '/results4.json'
    results = json.load(open(rp)) if os.path.exists(rp) else []
    results = [r for r in results if r['name'] != name] + [rec]
    json.dump(results, open(rp, 'w'), indent=1)
    print(f"== {name} == iso {npass}/12  /i/->{iso_res['i']['heard']!r}({'PASS' if iso_res['i']['pass'] else 'fail'})  /u/->{iso_res['u']['heard']!r}({'PASS' if iso_res['u']['pass'] else 'fail'})")
    print(f"   golden {rec['golden_mean']:.3f} {rec['golden_pass']}/4 | iF2band {rec['i_F2band']} uF2band {rec['u_F2band']} contrast {rec['i_minus_u_F2band']}dB")
    print('   iso:', {vp: (r['heard'], 'P' if r['pass'] else '.') for vp, r in iso_res.items()})
    print(f"SAVED {rp} ({len(results)} configs)")

if __name__ == '__main__':
    run(sys.argv[1])
