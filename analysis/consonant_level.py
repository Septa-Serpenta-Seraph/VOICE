#!/usr/bin/env python3
"""
VOICE — Consonant branch diagnostics.

Verifies that consonants are actually present in the rendered output and
measures their level relative to the vowels.

Usage:
    python consonant_level.py            # diagnose "This is the moon."
    python consonant_level.py --text "She sees the sun."
    python consonant_level.py --gain 0.5 # override CONSONANT_GAIN
"""

import argparse
import os
import sys

import numpy as np
from scipy.signal import welch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_plan import build_plan, SR
from frame_renderer import load_genome
import prosody_poststage as pp


def segment_rms(audio, seg, sr=SR):
    t0 = int(seg.t0 * sr)
    t1 = min(int(seg.t1 * sr), len(audio))
    if t1 <= t0:
        return 0.0
    chunk = audio[t0:t1]
    return float(np.sqrt(np.mean(chunk ** 2)))


def spectral_centroid(audio, t0, t1, sr=SR):
    i0 = int(t0 * sr)
    i1 = min(int(t1 * sr), len(audio))
    if i1 - i0 < 64:
        return 0.0
    freqs, psd = welch(audio[i0:i1], fs=sr, nperseg=min(1024, i1 - i0))
    total = np.sum(psd)
    if total <= 0:
        return 0.0
    return float(np.sum(freqs * psd) / total)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="This is the moon.")
    parser.add_argument("--gain", type=float, default=None)
    parser.add_argument("--out", default=None, help="write wav to this path")
    args = parser.parse_args()

    if args.gain is not None:
        pp.CONSONANT_GAIN = args.gain

    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    genome = load_genome(genome_path)

    plan = build_plan(args.text)
    audio = pp.render_plan_v3(plan, genome)

    print(f"text   : {args.text}")
    print(f"gain   : {pp.CONSONANT_GAIN}")
    print(f"output : {len(audio)} samples, peak {np.max(np.abs(audio)):.4f}, "
          f"rms {np.sqrt(np.mean(audio**2)):.4f}")
    print()
    print(f"{'i':>2}  {'phone':>5}  {'kind':>9}  {'t0':>6}  {'t1':>6}  {'rms':>8}  {'centroid':>9}")
    print("-" * 62)

    vowel_rms = []
    cons_rms = []
    for seg in plan.segments:
        rms = segment_rms(audio, seg)
        centroid = spectral_centroid(audio, seg.t0, seg.t1)
        if seg.kind in ("vowel", "diphthong"):
            vowel_rms.append(rms)
        elif seg.kind != "silence":
            cons_rms.append(rms)
        print(f"{seg.i:>2}  {seg.phone:>5}  {seg.kind:>9}  {seg.t0:>6.3f}  {seg.t1:>6.3f}  "
              f"{rms:>8.4f}  {centroid:>9.0f}")

    print("-" * 62)
    if vowel_rms and cons_rms:
        v = float(np.mean(vowel_rms))
        c = float(np.mean(cons_rms))
        delta_db = 20 * np.log10(c / v) if v > 0 and c > 0 else float("nan")
        print(f"mean vowel rms : {v:.4f}")
        print(f"mean cons  rms : {c:.4f}")
        print(f"consonant level: {delta_db:+.1f} dB rel. vowel")
    else:
        print("mean vowel rms : n/a")
        print("mean cons  rms : n/a")

    if args.out:
        from scipy.io import wavfile
        wavfile.write(args.out, SR, (audio * 32767).astype(np.int16))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
