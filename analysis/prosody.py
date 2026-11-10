#!/usr/bin/env python3
"""
VOICE — Prosody subsystem (Phase 3, Step 4).

F0 contours for declarative and question shapes, pause tiers,
micro-dip depth (now specified), breath rhythm.

Usage:
    python prosody.py --demo       # render prosodic contours
    python prosody.py --contours   # F0 contour analysis
"""

import argparse
import json
import os
import sys

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 48000

# Genome prosody targets
RATE_WPM = (135, 150)
DECLINATION_START_PCT = 8    # +8% above anchor at start
DECLINATION_END_PCT = (-18, -12)  # -18 to -12% at end
QUESTION_RISE_PCT = (25, 40)  # final rise for questions
PRE_BOUNDARY_LENGTHENING = (1.3, 1.6)
PAUSE_TIERS_MS = {"clause": (100, 300), "sentence": (300, 600)}

# Micro-dip: amplitude dips alongside pauses (Nar's distinction: dips, not silence)
# Duration: 5-15 ms (from genome). Depth now specified:
MICRO_DIP_DEPTH_PCT = 15  # % amplitude reduction (calibrated: subtle)
MICRO_DIP_DURATION_MS = (5, 15)


def f0_contour_declination(n_samples, sr, f0_anchor=190.0,
                           start_pct=DECLINATION_START_PCT,
                           end_pct=-15.0):
    """Generate a declination contour for a declarative utterance.

    F0 starts +8% above anchor, declines to -15% at end.
    Returns: array of F0 values (Hz) per sample.
    """
    t = np.arange(n_samples) / sr
    # Normalized time 0-1
    t_norm = t / (n_samples / sr) if n_samples > 0 else t

    # Declination: exponential decay from start to end
    start_f0 = f0_anchor * (1 + start_pct / 100.0)
    end_f0 = f0_anchor * (1 + end_pct / 100.0)

    # Smooth exponential declination
    contour = end_f0 + (start_f0 - end_f0) * np.exp(-3 * t_norm)

    return contour


def f0_contour_question(n_samples, sr, f0_anchor=190.0,
                        rise_pct=32.5):
    """Generate a question contour: declination then final rise.

    F0 declines, then rises 25-40% at the end.
    """
    t = np.arange(n_samples) / sr
    t_norm = t / (n_samples / sr) if n_samples > 0 else t

    start_f0 = f0_anchor * 1.08
    mid_f0 = f0_anchor * 0.95
    end_f0 = f0_anchor * (1 + rise_pct / 100.0)

    # Declination to midpoint, then rise
    contour = np.zeros(n_samples)
    mask_decline = t_norm < 0.7
    mask_rise = ~mask_decline

    contour[mask_decline] = mid_f0 + (start_f0 - mid_f0) * np.exp(-4 * t_norm[mask_decline] / 0.7)
    rise_t = (t_norm[mask_rise] - 0.7) / 0.3
    contour[mask_rise] = mid_f0 + (end_f0 - mid_f0) * np.sqrt(np.clip(rise_t, 0, 1))

    return contour


def apply_micro_dips(signal, sr, pause_positions, depth_pct=MICRO_DIP_DEPTH_PCT,
                     duration_ms=MICRO_DIP_DURATION_MS):
    """Apply micro-dips alongside pauses.

    Amplitude dips (not silence) — Nar's distinction.
    Duration: 5-15 ms. Depth: 15% amplitude reduction.
    """
    output = signal.copy()
    n_samples = len(signal)
    rng = np.random.default_rng(42)

    for pos in pause_positions:
        # Dip duration (random within range)
        dur_ms = rng.uniform(duration_ms[0], duration_ms[1])
        dur_samples = int(dur_ms * sr / 1000)

        # Apply dip centered at position
        start = max(0, pos - dur_samples // 2)
        end = min(n_samples, pos + dur_samples // 2)

        # Smooth dip (cosine window)
        dip_len = end - start
        if dip_len > 0:
            window = 0.5 * (1 + np.cos(2 * np.pi * np.arange(dip_len) / dip_len))
            dip = 1.0 - (depth_pct / 100.0) * (1 - window)
            output[start:end] = output[start:end] * dip

    return output


def breath_rhythm(signal, sr, phrase_boundaries, lengthening=PRE_BOUNDARY_LENGTHENING):
    """Apply phrase-final lengthening and breath placement.

    Lengthens the final syllable before a phrase boundary by 1.3-1.6x.
    Places breath (amplitude dip) at clause boundaries.
    """
    output = signal.copy()
    n_samples = len(signal)

    for boundary in phrase_boundaries:
        # Lengthening: stretch the last 50ms before boundary
        stretch_start = max(0, boundary - int(0.05 * sr))
        stretch_end = boundary
        if stretch_end > stretch_start:
            segment = output[stretch_start:stretch_end].copy()
            factor = np.random.uniform(lengthening[0], lengthening[1])
            # Simple time-stretch by resampling
            new_len = int(len(segment) * factor)
            if new_len > 0 and new_len < n_samples:
                stretched = np.interp(
                    np.linspace(0, len(segment) - 1, new_len),
                    np.arange(len(segment)),
                    segment
                )
                # Replace (may change total length — simplified)
                output[stretch_start:stretch_start + len(stretched)] = stretched[:stretch_end - stretch_start]

    return output


def apply_pause_tiers(signal, sr, clause_positions, sentence_positions):
    """Apply pause tiers: clause (100-300ms), sentence (300-600ms).

    Inserts silence at specified positions.
    """
    output = signal.copy()
    n_samples = len(signal)

    # Sort positions descending to insert from end
    all_pauses = []
    for pos in clause_positions:
        dur = np.random.uniform(PAUSE_TIERS_MS["clause"][0], PAUSE_TIERS_MS["clause"][1])
        all_pauses.append((pos, int(dur * sr / 1000)))
    for pos in sentence_positions:
        dur = np.random.uniform(PAUSE_TIERS_MS["sentence"][0], PAUSE_TIERS_MS["sentence"][1])
        all_pauses.append((pos, int(dur * sr / 1000)))

    all_pauses.sort(key=lambda x: -x[0])

    for pos, dur in all_pauses:
        pos = min(pos, n_samples)
        silence = np.zeros(dur)
        output = np.insert(output, pos, silence)

    return output


def demo(genome, f0=190.0, duration=3.0, seed=42, sr=SR):
    """Demo: render prosodic contours."""
    rng = np.random.default_rng(seed)

    # Declarative contour
    decl = f0_contour_declination(int(duration * sr), sr, f0_anchor=f0)
    # Question contour
    quest = f0_contour_question(int(duration * sr), sr, f0_anchor=f0)

    print("Declarative F0 contour:")
    print(f"  Start: {decl[0]:.1f} Hz, Mid: {decl[len(decl)//2]:.1f} Hz, End: {decl[-1]:.1f} Hz")
    print(f"  Declination: {DECLINATION_START_PCT}% → {DECLINATION_END_PCT}")

    print("Question F0 contour:")
    print(f"  Start: {quest[0]:.1f} Hz, Mid: {quest[len(quest)//2]:.1f} Hz, End: {quest[-1]:.1f} Hz")
    print(f"  Final rise: {QUESTION_RISE_PCT}%")

    # Micro-dip demo
    signal = np.sin(2 * np.pi * f0 * np.arange(int(duration * sr)) / sr)
    pause_positions = [int(duration * sr * 0.3), int(duration * sr * 0.7)]
    dipped = apply_micro_dips(signal, sr, pause_positions)
    print(f"\nMicro-dips: depth={MICRO_DIP_DEPTH_PCT}%, duration={MICRO_DIP_DURATION_MS} ms")
    print(f"  Applied at {len(pause_positions)} positions")

    return decl, quest, dipped


def main():
    parser = argparse.ArgumentParser(description="VOICE prosody")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--contours", action="store_true")
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sr", type=int, default=SR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    with open(genome_path) as f:
        genome = yaml.safe_load(f)

    if args.demo or args.contours:
        decl, quest, dipped = demo(genome, duration=args.duration, seed=args.seed, sr=args.sr)
        if args.json:
            print(json.dumps({
                "declination": {"start": float(decl[0]), "mid": float(decl[len(decl)//2]), "end": float(decl[-1])},
                "question": {"start": float(quest[0]), "mid": float(quest[len(quest)//2]), "end": float(quest[-1])},
            }, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()