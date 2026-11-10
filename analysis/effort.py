#!/usr/bin/env python3
"""
VOICE — Effort subsystem (Phase 3, Step 1).

Rd as the effort/quality control parameter. Implements:
- Rd sweep (0.3 → 1.3) with measurable differences
- Round 2 coupling: effort → small F0/F1 shifts
- High effort: Rd → 0.8, tilt flattens, harmonic energy rises
- Low effort: Rd → 1.3, breathier, softer

Usage:
    python effort.py --sweep          # Rd sweep with measurements
    python effort.py --demo           # render at effort levels
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

# Effort parameter mapping
EFFORT_RD_MAP = {
    # effort (0-1) → Rd
    # 0 = whisper/low effort, 1 = full/wildfire
    0.0: 1.3,   # whisper: breathy, soft
    0.25: 1.1,  # soft
    0.5: 0.9,   # normal
    0.75: 0.7,  # projected
    1.0: 0.5,   # wildfire: intense, bright
}

# Coupling: effort → F0/F1 shifts (Round 2 specification)
# High effort: F0 rises slightly, F1 rises slightly
EFFORT_F0_SHIFT_HZ = 5.0   # ±5 Hz at full effort
EFFORT_F1_SHIFT_HZ = 30.0  # ±30 Hz at full effort

# Tilt: high effort flattens tilt (less negative = brighter)
EFFORT_TILT_SHIFT = 0.5  # dB/oct flattening at full effort


def effort_to_rd(effort):
    """Map effort (0-1) to Rd value. Linear interpolation."""
    efforts = sorted(EFFORT_RD_MAP.keys())
    rds = [EFFORT_RD_MAP[e] for e in efforts]

    if effort <= efforts[0]:
        return rds[0]
    if effort >= efforts[-1]:
        return rds[-1]

    for i in range(len(efforts) - 1):
        if efforts[i] <= effort <= efforts[i + 1]:
            t = (effort - efforts[i]) / (efforts[i + 1] - efforts[i])
            return rds[i] + t * (rds[i + 1] - rds[i])

    return rds[-1]


def apply_effort_coupling(f0, f1, effort):
    """Apply effort → F0/F1 coupling (Round 2 spec).

    High effort: F0 rises, F1 rises.
    Low effort: F0 falls slightly, F1 falls.
    """
    f0_shift = (effort - 0.5) * 2 * EFFORT_F0_SHIFT_HZ
    f1_shift = (effort - 0.5) * 2 * EFFORT_F1_SHIFT_HZ
    return f0 + f0_shift, f1 + f1_shift


def synthesize_with_effort(genome, vowel, f0, duration, effort, source_kind="lf",
                           seed=42, sr=SR):
    """Synthesize a vowel at a given effort level."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from analysis.phase1_synth import load_genome, make_source, synthesize_vowel

    rd = effort_to_rd(effort)
    grid = genome["vowel_grid"][vowel]
    anchor = genome["filter"]["neutral_anchor"]

    # Base formants
    f1_base = grid[0]
    f2 = grid[1]
    f3 = grid[2]
    f4 = anchor["F4"]["hz"]

    # Apply effort coupling to F0 and F1
    f0_eff, f1_eff = apply_effort_coupling(f0, f1_base, effort)

    formants = {"F1": f1_eff, "F2": f2, "F3": f3, "F4": f4}

    # Bandwidths from genome
    bandwidths = {k: anchor[k]["bw"] for k in ["F1", "F2", "F3", "F4"]
                  if k in anchor and isinstance(anchor[k], dict)}

    # Generate source with effort-appropriate Rd
    # Use LF source with the effort's Rd
    sys.path.insert(0, os.path.dirname(__file__))
    from phase1_synth import lf_timing_from_rd

    tp, te, ta = lf_timing_from_rd(rd, f0_eff)

    # Generate LF pulse with effort
    rng = np.random.default_rng(seed)
    n_cycles = int(np.ceil(duration * f0_eff)) + 1
    from phase1_synth import _lf_alpha
    signal = np.zeros(int(duration * sr))
    pos = 0
    t0 = 1.0 / f0_eff
    alpha, omega, eps = _lf_alpha(tp, te, ta, t0)

    while pos < len(signal):
        period_samples = int(round(sr / f0_eff))
        period_samples = max(period_samples, 8)
        n = min(period_samples, len(signal) - pos)
        t = np.arange(n) / sr
        te_c = te
        val_te_open = np.exp(alpha * te_c) * np.sin(omega * te_c)
        denom = 1.0 - np.exp(-eps * (t0 - te_c))
        A = -val_te_open / denom if abs(denom) > 1e-10 else 0.0
        cyc = np.where(
            t < te_c,
            np.exp(alpha * t) * np.sin(omega * t),
            -A * (np.exp(-eps * (t - te_c)) - np.exp(-eps * (t0 - te_c))),
        )
        signal[pos:pos + n] += cyc
        pos += period_samples

    source = signal[:int(duration * sr)]

    # Synthesize with formant bank
    out = synthesize_vowel(f0_eff, formants, duration, sr, source=source,
                           bandwidths=bandwidths)

    return out, f0_eff, f1_eff, rd


def measure_effort(render_path):
    """Measure a render with HEARING's pipeline."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "narusya-hearing", "analysis"))
    from autonomous_eval import measure_render
    return measure_render(render_path)


def sweep(genome, vowel="ɑ", f0=190.0, duration=2.0, seed=42, sr=SR):
    """Sweep effort from 0 to 1 in steps, render and measure."""
    efforts = [0.0, 0.25, 0.5, 0.75, 1.0]
    results = []

    out_dir = os.path.join(os.path.dirname(__file__), "..", "renders", "effort")
    os.makedirs(out_dir, exist_ok=True)

    for effort in efforts:
        sig, f0_eff, f1_eff, rd = synthesize_with_effort(
            genome, vowel, f0, duration, effort, seed=seed, sr=sr
        )

        fname = f"effort_{effort:.2f}_rd{rd:.2f}.wav"
        fpath = os.path.join(out_dir, fname)
        from scipy.io import wavfile
        wavfile.write(fpath, sr, (sig * 32767).astype(np.int16))

        # Measure
        try:
            meas = measure_effort(fpath)
        except Exception as e:
            meas = {"error": str(e)}

        result = {
            "effort": effort,
            "rd": round(rd, 3),
            "f0": round(f0_eff, 1),
            "f1": round(f1_eff, 1),
            "f0_shift": round(f0_eff - f0, 1),
            "f1_shift": round(f1_eff - grid_f1(genome, vowel), 1),
            "measurements": meas,
        }
        results.append(result)

        print(f"effort={effort:.2f}  Rd={rd:.3f}  F0={f0_eff:.1f}  F1={f1_eff:.1f}  "
              f"tilt={meas.get('tilt', 'N/A')}  hnr={meas.get('hnr', 'N/A')}")

    return results


def grid_f1(genome, vowel):
    return genome["vowel_grid"][vowel][0]


def main():
    parser = argparse.ArgumentParser(description="VOICE effort subsystem")
    parser.add_argument("--sweep", action="store_true", help="Rd effort sweep")
    parser.add_argument("--demo", action="store_true", help="Render effort levels")
    parser.add_argument("--vowel", default="ɑ")
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sr", type=int, default=SR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    with open(genome_path) as f:
        genome = yaml.safe_load(f)

    if args.sweep:
        results = sweep(genome, vowel=args.vowel, duration=args.duration,
                        seed=args.seed, sr=args.sr)

        if args.json:
            print(json.dumps(results, indent=2))

        # Save results
        out_path = os.path.join(os.path.dirname(__file__), "..", "renders",
                                "effort", "effort_sweep.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults: {out_path}")

        # Check measurability
        tilts = [r["measurements"].get("tilt") for r in results if "tilt" in r.get("measurements", {})]
        hnr = [r["measurements"].get("hnr") for r in results if "hnr" in r.get("measurements", {})]
        if len(tilts) >= 2:
            tilt_range = max(tilts) - min(tilts)
            print(f"Tilt range across effort: {tilt_range:.3f} dB/oct")
            print(f"HNR range across effort: {max(hnr)-min(hnr):.2f} dB")
            if tilt_range > 0.1:
                print("PASS: Effort produces measurable tilt differences")
            else:
                print("WARN: Effort tilt differences may be too small")

    elif args.demo:
        for effort in [0.0, 0.5, 1.0]:
            sig, f0_eff, f1_eff, rd = synthesize_with_effort(
                genome, args.vowel, 190.0, args.duration, effort, seed=args.seed, sr=args.sr
            )
            print(f"effort={effort:.1f}  Rd={rd:.3f}  F0={f0_eff:.1f}  F1={f1_eff:.1f}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()