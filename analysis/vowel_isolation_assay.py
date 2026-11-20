#!/usr/bin/env python3
"""Vowel isolation assay — phoneme-level intelligibility floor (Round 19).

Before sentence WER, require each vowel to be recognizable in isolation as
itself. Renders each of the 12 genome vowels alone (250 ms, no onset) through
the full render_plan_v3 chain, transcribes with the independent gate1 oracle
(faster-whisper-base), and judges via the vendored CMUdict g2p: the heard
word's vowel must match the target's front/back + height category. The collapse
mode /i/ -> "You" (/u/) scores FAIL, not pass.

Why this gate: sentence WER averages the deficit across a whole utterance and
Whisper's language model rescues canonical phrases from weak acoustics (the
"golden island"). The isolation assay is cheap, absolute, and localizes the
deficit to specific phonemes. If a vowel is not a phoneme alone, no bridge or
prosody will make it a phoneme in company.

Baseline (791ce3a, Round 17): 1/12 — only /u/ -> "You" passes; the other 11
vowels transcribe as silence. Every static spectral lever tested in Round 19
(F2/F3 bandwidth 200-400 Hz, aspiration -14..-30 dB, high-shelf brightening
+20 dB, and combinations) scored 0/12 and broke /u/. See
reviews/round_19_isolation_assay.md.

Usage:
    python vowel_isolation_assay.py            # report to stdout
    python vowel_isolation_assay.py --json P   # also write JSON report
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
from render_plan import Style, SR, RenderPlan, Segment
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
    g = genome['vowel_grid'][vp]
    seg = Segment(i=0, phone=vp, kind='vowel', t0=0.0, t1=0.25, word=0, syll=0,
                  stress=1, voiced=True,
                  targets={'F1': g[0], 'F2': g[1], 'F3': g[2], 'F4': 3100})
    plan = RenderPlan(text=vp, words=[vp], segments=[seg], style=Style(seed=42))
    a = render_plan_v3(plan, genome)
    p = os.path.join(outdir, f'{tag}_{vp}.wav')
    wavfile.write(p, SR, (np.clip(a, -1, 1) * 32767).astype('int16'))
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', help='write JSON report to this path')
    ap.add_argument('--outdir', default='/tmp/vowel_iso')
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    with open(os.path.join(HERE, '..', 'genome', 'voice_genome.yaml')) as f:
        genome = yaml.safe_load(f)
    paths = [render_iso(vp, genome, args.outdir) for vp in VOWELS]
    hyps = g1.transcribe(paths)
    res, npass = {}, 0
    for vp, h in zip(VOWELS, hyps):
        ok, vs = iso_pass(vp, h)
        npass += ok
        res[vp] = {'heard': h, 'pass': ok, 'heard_vowels': sorted(vs)}
        print(f"  /{vp}/ -> {h!r:14s} {'PASS' if ok else 'fail'}  vowels={sorted(vs)}")
    report = {'oracle': 'faster-whisper-base', 'assay': 'vowel-isolation',
              'passed': npass, 'total': len(VOWELS), 'vowels': res}
    print(f"Vowel isolation: {npass}/{len(VOWELS)} recognizable as themselves.")
    print("OVERALL:", "PASS" if npass == len(VOWELS) else "FAIL")
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print("Report:", args.json)


if __name__ == '__main__':
    main()
