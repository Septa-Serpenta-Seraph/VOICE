#!/usr/bin/env python3
"""
VOICE — AM family subsystem (Phase 3, Step 2).

Sub-bass purr (pitch-locked F0/2, LFO 3-5 Hz) + wolf warmth (slow AM
3-5 Hz) as one subsystem with the 8% combined slow-AM cap enforced
in code (structural limit, not guideline).

Calibration protocol (§2 of Round 10 brief):
- Depth ladder: render at depths 0→max in steps, measure HEARING
  discrimination threshold, set genome at ~70%.

Usage:
    python am_family.py --ladder    # depth ladder for calibration
    python am_family.py --demo      # render with AM at genome depths
"""

import argparse
import json
import os
import sys

import numpy as np
from scipy.signal import lfilter
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 48000

# Genome AM parameters (proposals — to be calibrated)
SUB_BASS_LFO_HZ = 4.0       # midpoint of [3, 5]
SUB_BASS_DEPTH_PCT = 5.0    # proposal (Round 3)
WOLF_WARMTH_HZ = 4.0         # midpoint of [3, 5]
WOLF_WARMTH_DEPTH_PCT = 3.0  # proposal (Round 3)
COMBINED_CAP_PCT = 8.0       # structural limit


def enforce_cap(sub_depth, wolf_depth):
    """Enforce combined slow-AM cap. Returns adjusted depths."""
    total = sub_depth + wolf_depth
    if total > COMBINED_CAP_PCT:
        scale = COMBINED_CAP_PCT / total
        return sub_depth * scale, wolf_depth * scale
    return sub_depth, wolf_depth


def sub_bass_purr(signal, sr, f0, lfo_hz=SUB_BASS_LFO_HZ,
                  depth_pct=SUB_BASS_DEPTH_PCT, gate_sustained=True):
    """Sub-bass purr: pitch-locked F0/2 with LFO modulation.

    Adds a subharmonic at F0/2 (≈95 Hz at F0 190) with slow LFO.
    Only applied to sustained voiced segments.
    """
    n_samples = len(signal)
    t = np.arange(n_samples) / sr

    # Subharmonic at F0/2
    sub_freq = f0 / 2.0
    sub_signal = np.sin(2 * np.pi * sub_freq * t)

    # LFO modulation (slow amplitude wander)
    lfo = 1.0 + (depth_pct / 100.0) * np.sin(2 * np.pi * lfo_hz * t)

    # Apply LFO to subharmonic
    sub_modulated = sub_signal * lfo * (depth_pct / 100.0)

    # Add to signal (sub-bass is additive, low level)
    level = 10 ** (-18 / 20.0)  # -18 dB ≈ 13% of main signal
    output = signal + sub_modulated * level

    return output


def wolf_warmth(signal, sr, am_hz=WOLF_WARMTH_HZ,
                depth_pct=WOLF_WARMTH_DEPTH_PCT):
    """Wolf warmth: slow AM at 3-5 Hz.

    Applies slow amplitude modulation to the signal.
    """
    n_samples = len(signal)
    t = np.arange(n_samples) / sr

    # Slow AM
    am = 1.0 + (depth_pct / 100.0) * np.sin(2 * np.pi * am_hz * t)

    output = signal * am
    return output


def apply_am_family(signal, sr, f0, sub_depth=None, wolf_depth=None,
                    sub_lfo_hz=SUB_BASS_LFO_HZ, wolf_am_hz=WOLF_WARMTH_HZ):
    """Apply both AM effects with cap enforcement.

    Returns: (output, adjusted_sub_depth, adjusted_wolf_depth)
    """
    if sub_depth is None:
        sub_depth = SUB_BASS_DEPTH_PCT
    if wolf_depth is None:
        wolf_depth = WOLF_WARMTH_DEPTH_PCT

    # Enforce combined cap
    adj_sub, adj_wolf = enforce_cap(sub_depth, wolf_depth)

    output = signal.copy()
    output = sub_bass_purr(output, sr, f0, lfo_hz=sub_lfo_hz, depth_pct=adj_sub)
    output = wolf_warmth(output, sr, am_hz=wolf_am_hz, depth_pct=adj_wolf)

    return output, adj_sub, adj_wolf


def depth_ladder(genome, vowel="ɑ", f0=190.0, duration=2.0, seed=42, sr=SR):
    """Depth ladder for AM calibration.

    Renders at depths from 0 to max in steps, measures HEARING
    discrimination. Returns ladder results.
    """
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "narusya-hearing", "analysis"))
    from autonomous_eval import measure_render

    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from phase1_synth import load_genome, make_source, synthesize_vowel

    genome = load_genome(os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml"))

    # Base render (clean, no AM)
    rng = np.random.default_rng(seed)
    source = make_source(genome, f0, duration, "lf", rng)
    anchor = genome["filter"]["neutral_anchor"]
    grid = genome["vowel_grid"][vowel]
    formants = {"F1": grid[0], "F2": grid[1], "F3": grid[2], "F4": anchor["F4"]["hz"]}
    bandwidths = {k: anchor[k]["bw"] for k in ["F1", "F2", "F3", "F4"] if k in anchor and isinstance(anchor[k], dict)}
    clean = synthesize_vowel(f0, formants, duration, sr, source=source, bandwidths=bandwidths)

    out_dir = os.path.join(os.path.dirname(__file__), "..", "renders", "am_family")
    os.makedirs(out_dir, exist_ok=True)

    # Depth steps: 0 (clean), then 2%, 4%, 6%, 8%, 10%, 12%
    depths = [0, 2, 4, 6, 8, 10, 12]
    results = []

    for depth in depths:
        if depth == 0:
            sig = clean.copy()
            sub_d, wolf_d = 0, 0
        else:
            # Split depth between sub and wolf (sub gets 5/8, wolf gets 3/8)
            sub_d = depth * (5.0 / 8.0)
            wolf_d = depth * (3.0 / 8.0)
            adj_sub, adj_wolf = enforce_cap(sub_d, wolf_d)
            sig, _, _ = apply_am_family(clean.copy(), sr, f0, sub_depth=adj_sub, wolf_depth=adj_wolf)

        fname = f"am_depth_{depth:02d}.wav"
        fpath = os.path.join(out_dir, fname)
        from scipy.io import wavfile
        wavfile.write(fpath, sr, (sig * 32767).astype(np.int16))

        try:
            meas = measure_render(fpath)
        except Exception as e:
            meas = {"error": str(e)}

        results.append({
            "depth_pct": depth,
            "sub_depth": round(sub_d, 2) if depth > 0 else 0,
            "wolf_depth": round(wolf_d, 2) if depth > 0 else 0,
            "measurements": meas,
        })
        print(f"depth={depth:2d}%  tilt={meas.get('tilt', 'N/A')}  hnr={meas.get('hnr', 'N/A')}  mfcc[0]={meas.get('mfcc', [0])[0] if meas.get('mfcc') else 'N/A'}")

    return results


def demo(genome, vowel="ɑ", f0=190.0, duration=2.0, seed=42, sr=SR):
    """Render with AM at genome proposal depths."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from phase1_synth import load_genome, make_source, synthesize_vowel

    rng = np.random.default_rng(seed)
    source = make_source(genome, f0, duration, "lf", rng)
    anchor = genome["filter"]["neutral_anchor"]
    grid = genome["vowel_grid"][vowel]
    formants = {"F1": grid[0], "F2": grid[1], "F3": grid[2], "F4": anchor["F4"]["hz"]}
    bandwidths = {k: anchor[k]["bw"] for k in ["F1", "F2", "F3", "F4"] if k in anchor and isinstance(anchor[k], dict)}
    clean = synthesize_vowel(f0, formants, duration, sr, source=source, bandwidths=bandwidths)

    # Apply AM at proposal depths
    sub_d = 5.0
    wolf_d = 3.0
    adj_sub, adj_wolf = enforce_cap(sub_d, wolf_d)
    am_sig, _, _ = apply_am_family(clean.copy(), sr, f0, sub_depth=adj_sub, wolf_depth=adj_wolf)

    out_dir = os.path.join(os.path.dirname(__file__), "..", "renders", "am_family")
    os.makedirs(out_dir, exist_ok=True)
    from scipy.io import wavfile
    wavfile.write(os.path.join(out_dir, "am_clean.wav"), sr, (clean * 32767).astype(np.int16))
    wavfile.write(os.path.join(out_dir, "am_applied.wav"), sr, (am_sig * 32767).astype(np.int16))

    print(f"Sub-bass depth: {adj_sub:.2f}% (proposal: {sub_d}%)")
    print(f"Wolf warmth depth: {adj_wolf:.2f}% (proposal: {wolf_d}%)")
    print(f"Combined: {adj_sub + adj_wolf:.2f}% (cap: {COMBINED_CAP_PCT}%)")
    print(f"Saved: am_clean.wav, am_applied.wav")

    return clean, am_sig


def main():
    parser = argparse.ArgumentParser(description="VOICE AM family")
    parser.add_argument("--ladder", action="store_true", help="Depth ladder for calibration")
    parser.add_argument("--demo", action="store_true", help="Render with AM at proposal depths")
    parser.add_argument("--vowel", default="ɑ")
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sr", type=int, default=SR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    with open(genome_path) as f:
        genome = yaml.safe_load(f)

    if args.ladder:
        results = depth_ladder(genome, vowel=args.vowel, duration=args.duration,
                               seed=args.seed, sr=args.sr)
        if args.json:
            print(json.dumps(results, indent=2))
        out_path = os.path.join(os.path.dirname(__file__), "..", "renders",
                                "am_family", "am_ladder.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nLadder: {out_path}")

    elif args.demo:
        demo(genome, vowel=args.vowel, duration=args.duration, seed=args.seed, sr=args.sr)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()