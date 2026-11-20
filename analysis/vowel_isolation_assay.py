#!/usr/bin/env python3
"""Vowel phoneme assay — hVd carrier-frame intelligibility floor (Round 21).

CORRECTION (Round 21): the original Round 19 "bare-vowel isolation" gate (250 ms
vowel, no onset) is INVALID as an intelligibility floor. A natural-speech control
showed the Nar clone ALSO fails it: natural /i/ -> "", natural /u/ -> "" at
250 ms. Whisper is a WORD recognizer; a bare 250 ms vowel is not a word, so the
oracle fails on natural speech too. A gate that natural speech fails cannot grade
the synth. The bare-vowel render is kept only as a spectral diagnostic (--bare),
never as the intelligibility gate.

VALID floor: the Hillenbrand hVd carrier frame (heed/hid/head/had/hod/hud/hood/
who'd). The vowel sits in a real word with a constant h_d consonant frame, so the
oracle can transcribe it and recognition differences are attributable to the
vowel. Judge the heard word's vowel phoneme (vendored CMUdict g2p) against the
target's front/back + height category; /i/ -> "you" (/u/) scores FAIL.

Validated: natural Nar clone 6/8 categories; genome synth (5caa7ec) 2/8. The
deficit is real (synth well below natural) but NOT "0/12, no vowel is a phoneme"
— that was the invalid instrument. Synth /ɛ/ and /u/ pass in context; /i/ shows
the front-vowel back-collapse (heed -> "you"). See reviews/round_21_assay_correction.md.

Usage:
    python vowel_isolation_assay.py                 # synth hVd gate
    python vowel_isolation_assay.py --json P        # also write JSON report
    python vowel_isolation_assay.py --natural DIR   # judge natural hVd refs in DIR
    python vowel_isolation_assay.py --bare          # bare-vowel SPECTRAL diagnostic (not a gate)
"""
import argparse
import json
import os
import re
import sys

import numpy as np
import yaml
from scipy.io import wavfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from render_plan import Style, SR, RenderPlan, Segment, build_plan
from prosody_poststage import render_plan_v3
import gate1_intelligibility as g1
from lexicon import g2p_word, _is_vowel_ipa

VOWELS = ['i', '\u026a', 'e', '\u025b', '\u00e6', '\u0251', '\u028c',
          '\u0254', 'o', '\u028a', 'u', '\u0259']

# front/back + height category sets. The collapse mode is front -> back, so
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
_VCHARS = 'i\u026ae\u025b\u00e6\u0251\u028c\u0254o\u028au\u0259'

# Hillenbrand hVd carrier word -> target vowel phoneme.
HVD = [('heed', 'i'), ('hid', '\u026a'), ('head', '\u025b'), ('had', '\u00e6'),
       ('hod', '\u0251'), ('hud', '\u028c'), ('hood', '\u028a'), ("who'd", 'u')]


def heard_vowels(heard):
    """Vowel phones present in the heard transcription (g2p + letter fallback)."""
    vs = set()
    for tok in re.findall(r"[a-z]+", heard.lower()):
        if len(tok) == 1 and tok in LETTER_V:
            vs.add(LETTER_V[tok])
            continue
        try:
            phones, _, _ = g2p_word(tok)
        except Exception:
            continue
        for ph in phones:
            if _is_vowel_ipa(ph):
                vs.add(ph)
            else:
                for ch in ph:
                    if ch in _VCHARS:
                        vs.add(ch)
    return vs


def iso_pass(vp, heard):
    if not heard.strip():
        return False, set()
    vs = heard_vowels(heard)
    return bool(vs & CAT[vp]), vs


def render_iso(vp, genome, outdir, tag='iso'):
    """Bare-vowel render — SPECTRAL DIAGNOSTIC ONLY, not the intelligibility gate."""
    g = genome['vowel_grid'][vp]
    seg = Segment(i=0, phone=vp, kind='vowel', t0=0.0, t1=0.25, word=0, syll=0,
                  stress=1, voiced=True,
                  targets={'F1': g[0], 'F2': g[1], 'F3': g[2], 'F4': 3100})
    plan = RenderPlan(text=vp, words=[vp], segments=[seg], style=Style(seed=42))
    a = render_plan_v3(plan, genome)
    p = os.path.join(outdir, f'{tag}_{vp}.wav')
    wavfile.write(p, SR, (np.clip(a, -1, 1) * 32767).astype('int16'))
    return p


def run_hvd(genome, outdir, natural_dir=None):
    paths, words, targets = [], [], []
    for w, vp in HVD:
        if natural_dir:
            p = os.path.join(natural_dir, f"nat_{w.replace(chr(39), '')}.wav")
            if not os.path.exists(p):
                continue
        else:
            a = render_plan_v3(build_plan(w, style=Style(seed=42)), genome)
            p = os.path.join(outdir, f"hvd_{w.replace(chr(39), '')}.wav")
            wavfile.write(p, SR, (np.clip(a, -1, 1) * 32767).astype('int16'))
        paths.append(p); words.append(w); targets.append(vp)
    hyps = g1.transcribe(paths)
    rows, npass = {}, 0
    for w, vp, h in zip(words, targets, hyps):
        ok, vs = iso_pass(vp, h)
        npass += ok
        rows[w] = {'target': vp, 'heard': h, 'pass': ok, 'heard_vowels': sorted(vs)}
        print(f"  {w:6s} /{vp}/ -> {h!r:16s} {'PASS' if ok else 'fail'}  v={sorted(vs)}")
    return npass, len(words), rows


def run_bare(genome, outdir):
    paths = [render_iso(vp, genome, outdir) for vp in VOWELS]
    hyps = g1.transcribe(paths)
    rows, npass = {}, 0
    for vp, h in zip(VOWELS, hyps):
        ok, vs = iso_pass(vp, h)
        npass += ok
        rows[vp] = {'heard': h, 'pass': ok}
        print(f"  /{vp}/ -> {h!r:14s} {'PASS' if ok else 'fail'}")
    print("  (bare-vowel diagnostic: NOT a valid intelligibility gate; natural speech fails it too)")
    return npass, len(VOWELS), rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', help='write JSON report to this path')
    ap.add_argument('--outdir', default='/tmp/vowel_iso')
    ap.add_argument('--natural', help='directory of natural nat_<word>.wav hVd references')
    ap.add_argument('--bare', action='store_true', help='bare-vowel spectral diagnostic (not a gate)')
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    with open(os.path.join(HERE, '..', 'genome', 'voice_genome.yaml')) as f:
        genome = yaml.safe_load(f)
    if args.bare:
        npass, total, rows = run_bare(genome, args.outdir)
        assay = 'bare-vowel-diagnostic'
    else:
        npass, total, rows = run_hvd(genome, args.outdir, args.natural)
        assay = 'hVd-carrier'
    label = 'natural' if args.natural else ('bare' if args.bare else 'synth')
    print(f"Vowel phoneme assay ({assay}, {label}): {npass}/{total}.")
    if not args.bare:
        print("OVERALL:", "PASS" if npass == total else "FAIL")
    report = {'oracle': 'faster-whisper-base', 'assay': assay, 'source': label,
              'passed': npass, 'total': total, 'items': rows}
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print("Report:", args.json)


if __name__ == '__main__':
    main()
