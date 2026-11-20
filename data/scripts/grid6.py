#!/usr/bin/env python3
"""Round 21 CORRECTION — hVd carrier-frame vowel assay (valid floor).

The bare-vowel isolation assay (250 ms, no onset) is INVALID: the natural Nar
clone also fails it (natural /i/ -> "", /u/ -> ""). Whisper is a WORD recognizer;
a bare 250 ms vowel is not a word, so it fails on natural speech too. A gate that
natural speech fails cannot grade the synth.

Corrected floor: Hillenbrand hVd carrier words (heed/hid/head/had/hod/hud/hood/
who'd). The vowel lives in a real word whisper can transcribe; judge the heard
word's vowel phoneme (CMUdict g2p) against the target's front/back+height
category. Natural voice passes most categories; this is a valid instrument.

Usage: PYTHONPATH= /mnt/data/pocket-tts-venv/bin/python grid6.py <natural|synth>
"""
import sys, os, json, time
V = '/mnt/data/nar-r17/voice'
sys.path.insert(0, V + '/analysis')
import numpy as np, yaml
from scipy.io import wavfile
from render_plan import build_plan, Style, SR
import prosody_poststage as pp
import gate1_intelligibility as g1
import vowel_isolation_assay as assay

EXP = '/mnt/data/nar-r17'
WAVS = EXP + '/wavs'
genome = yaml.safe_load(open(V + '/genome/voice_genome.yaml'))

# hVd carrier word -> target vowel phoneme
HVD = [('heed', 'i'), ('hid', '\u026a'), ('head', '\u025b'), ('had', '\u00e6'),
       ('hod', '\u0251'), ('hud', '\u028c'), ('hood', '\u028a'), ("who'd", 'u')]


def judge(word_target, heard):
    """Pass if the heard word's vowel matches the target vowel category."""
    vp = word_target
    if not heard.strip():
        return False, set()
    vs = assay.heard_vowels(heard)
    return bool(vs & assay.CAT[vp]), vs


def run(mode):
    t0 = time.time()
    paths, targets, words = [], [], []
    for w, vp in HVD:
        if mode == 'natural':
            fn = w.replace("'", '')
            p = f'{EXP}/nat_{fn}.wav'
            if not os.path.exists(p):
                continue
        else:
            a = pp.render_plan_v3(build_plan(w, style=Style(seed=42)), genome)
            p = f'{WAVS}/hvd_{w.replace(chr(39),"")}.wav'
            wavfile.write(p, SR, (np.clip(a, -1, 1)*32767).astype('int16'))
        paths.append(p); targets.append(vp); words.append(w)
    hyps = g1.transcribe(paths)
    rows, npass = {}, 0
    for w, vp, h in zip(words, targets, hyps):
        ok, vs = judge(vp, h)
        npass += ok
        rows[w] = {'target': vp, 'heard': h, 'pass': ok, 'heard_vowels': sorted(vs)}
    rec = {'mode': mode, 'assay': 'hVd-carrier', 'pass': npass, 'total': len(words),
           'words': rows, 'render_s': round(time.time()-t0, 1)}
    rp = EXP + '/results6.json'
    results = json.load(open(rp)) if os.path.exists(rp) else []
    results = [r for r in results if r['mode'] != mode] + [rec]
    json.dump(results, open(rp, 'w'), indent=1, ensure_ascii=False)
    print(f"== {mode} hVd == {npass}/{len(words)}")
    for w, r in rows.items():
        print(f"  {w:6s} /{r['target']}/ -> {r['heard']!r:14s} {'PASS' if r['pass'] else 'fail'}  v={r['heard_vowels']}")
    print(f"SAVED {rp}")


if __name__ == '__main__':
    run(sys.argv[1])
