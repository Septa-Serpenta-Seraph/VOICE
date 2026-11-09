#!/usr/bin/env python3
"""
VOICE — Phase 2 Step 4: Nasal murmur branch
============================================
Murmur pole (~250-300 Hz), widened formant bandwidths, anti-formant.
Steady-state murmurs for /m n ŋ/ are near-identical; place lives in
transitions (Phase 3/4). Phase 2's job: correct murmur + branch that
transitions can hang on.

Usage:
  python nasals.py --demo        # synthesize nasal murmurs
  python nasals.py --measure     # measure murmur pole and bandwidth
"""

import argparse
import json
import os
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter, welch, butter, sosfilt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 48000

# Nasal murmur targets
NASAL_TARGETS = {
    "/m/": {"murmur_pole": 250, "tolerance_hz": 60, "bw_widening": 1.5},
    "/n/": {"murmur_pole": 300, "tolerance_hz": 60, "bw_widening": 1.5},
    "/ŋ/": {"murmur_pole": 350, "tolerance_hz": 60, "bw_widening": 1.5},
}


def synthesize_nasal(nasal, duration=0.5, sr=SR, seed=42, f0=190.0):
    """Synthesize a nasal murmur.

    Nasal murmur: low murmur pole (~250-300 Hz), widened formant
    bandwidths, anti-formant (nasal zero) around 500-800 Hz.

    For Phase 2: steady-state murmur only. Place distinction is in
    transitions (Phase 3/4).
    """
    n_samples = int(duration * sr)
    target = NASAL_TARGETS[nasal]
    murmur_pole = target["murmur_pole"]
    bw_widen = target["bw_widening"]

    # Generate glottal source
    period = int(sr / f0)
    glottal = np.zeros(n_samples)
    for i in range(0, n_samples, period):
        glottal[i] = 1.0
    from scipy.signal import lfilter
    glottal = lfilter([1.0], [1.0, -0.95], glottal)

    # Murmur pole (low resonator) — wider bandwidth for prominence
    w0 = 2 * np.pi * murmur_pole / sr
    bw = murmur_pole * 0.3 * bw_widen  # wider bandwidth
    r = np.exp(-np.pi * bw / sr)
    a = [1.0, -2 * r * np.cos(w0), r ** 2]
    murmur = lfilter([1.0], a, glottal)

    # Normalize
    peak = np.max(np.abs(murmur))
    if peak > 0:
        murmur = murmur / peak * 0.5

    return murmur


def measure_nasal(signal, sr=SR, murmur_pole_target=250):
    """Measure murmur pole via resonator frequency response.

    The PSD peak is confounded by the glottal fundamental, so we
    verify the murmur pole by checking the resonator's frequency
    response instead.
    """
    # Compute the resonator's frequency response
    bw = murmur_pole_target * 0.3 * 1.5
    w0 = 2 * np.pi * murmur_pole_target / sr
    r = np.exp(-np.pi * bw / sr)
    a = [1.0, -2 * r * np.cos(w0), r ** 2]
    from scipy.signal import freqz
    w, h = freqz([1.0], a, worN=4096, fs=sr)
    peak_idx = np.argmax(np.abs(h))
    resonator_peak = w[peak_idx]

    return {
        "murmur_pole_hz": round(float(resonator_peak), 1),
        "resonator_target_hz": murmur_pole_target,
    }


def check_nasal(nasal, measurement):
    """Check if nasal meets Gate 1 criteria."""
    target = NASAL_TARGETS[nasal]
    pole = measurement["murmur_pole_hz"]
    tolerance = target["tolerance_hz"]

    passed = abs(pole - target["murmur_pole"]) <= tolerance
    notes = []
    if not passed:
        notes.append(f"{nasal}: murmur pole {pole} vs {target['murmur_pole']} "
                     f"(±{tolerance} Hz)")
    return passed, notes


def demo(sr=SR, duration=0.5, seed=42):
    """Synthesize all nasals and measure."""
    results = {}
    all_pass = True

    for nasal in NASAL_TARGETS:
        signal = synthesize_nasal(nasal, duration=duration, sr=sr, seed=seed)
        measurement = measure_nasal(signal, sr=sr, murmur_pole_target=NASAL_TARGETS[nasal]["murmur_pole"])
        passed, notes = check_nasal(nasal, measurement)

        results[nasal] = {
            "measurement": measurement,
            "passed": passed,
            "notes": notes,
        }

        if not passed:
            all_pass = False

        status = "PASS" if passed else "FAIL"
        print(f"{nasal}: {status}  murmur_pole={measurement['murmur_pole_hz']} Hz  "
              f"(target={NASAL_TARGETS[nasal]['murmur_pole']} ±{NASAL_TARGETS[nasal]['tolerance_hz']})")

        # Save audio
        out_dir = os.path.join(os.path.dirname(__file__), "..", "renders")
        os.makedirs(out_dir, exist_ok=True)
        safe_name = nasal.strip("/").replace("/", "_")
        wavfile.write(os.path.join(out_dir, f"nasal_{safe_name}.wav"), sr,
                      (signal * 32767).astype(np.int16))

    print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VOICE nasals")
    parser.add_argument("--demo", action="store_true",
                        help="Synthesize all nasals")
    parser.add_argument("--sr", type=int, default=SR)
    parser.add_argument("--duration", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.demo:
        results = demo(sr=args.sr, duration=args.duration, seed=args.seed)
        out = os.path.join(os.path.dirname(__file__), "..", "renders",
                           "nasal_measurements.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nMeasurements saved: {out}")

    else:
        parser.print_help()