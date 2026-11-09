#!/usr/bin/env python3
"""
Phase 0 Round-Trip Test

Synthesizes a 1-second /ɑ/ vowel at genome defaults, measures it with
the corrected harness, and verifies recovery within Gate 0 tolerances.

Genome defaults for /ɑ/:
  F0: 190 Hz
  F1: 800 Hz, F2: 1150 Hz, F3: 2400 Hz, F4: 3100 Hz

Gate 0 tolerances:
  F0: ±3 Hz
  Formants: ±5%

Usage:
    /mnt/data/pocket-tts-venv/bin/python round_trip_test.py
"""

import numpy as np
import soundfile as sf
import os
import sys
import json

# Add analysis dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_voice import (
    measure_f0, measure_formants, measure_harmonicity,
    measure_jitter_shimmer, measure_spectral_tilt, measure_mfcc,
)

# ── Genome defaults for /ɑ/ ────────────────────────────────────────────────
F0 = 190.0
FORMANTS = {"F1": 800.0, "F2": 1150.0, "F3": 2400.0, "F4": 3100.0}
DURATION = 1.0
SR = 48000
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "round_trip_alpha.wav")


def synthesize_vowel(f0, formants, duration, sr):
    """Synthesize a vowel using a simple formant (cascade) synthesizer.

    Approach: generate glottal pulse train, apply formant resonators,
    add radiation characteristic.
    """
    n_samples = int(duration * sr)
    t = np.arange(n_samples) / sr

    # 1. Glottal source: pulse train at F0
    period = int(sr / f0)
    source = np.zeros(n_samples)
    for i in range(0, n_samples, period):
        source[i] = 1.0
    # Apply glottal pulse shape (simple: decay after each pulse)
    # Use a one-pole filter to smooth
    from scipy.signal import lfilter
    glottal = lfilter([1.0], [1.0, -0.95], source)

    # 2. Formant resonators (cascade of 2nd-order IIR)
    signal = glottal.copy()
    for f_name, f_freq in formants.items():
        # Bandwidth ~10% of frequency (reasonable for vowels)
        bw = f_freq * 0.1
        # 2nd-order resonator
        w0 = 2 * np.pi * f_freq / sr
        r = np.exp(-np.pi * bw / sr)
        b = [1 - r, 0, 0]  # numerator
        # Standard formant resonator: H(z) = 1 / (1 - 2r*cos(w0)*z^-1 + r^2*z^-2)
        a = [1.0, -2 * r * np.cos(w0), r**2]
        signal = lfilter([1.0], a, signal)

    # 3. Radiation: +6 dB/oct high-freq boost (simple high-shelf)
    # Apply a simple differentiator
    signal = np.diff(signal, prepend=signal[0])

    # 4. Normalize
    peak = np.max(np.abs(signal))
    if peak > 0:
        signal = signal / peak * 0.5

    return signal


def main():
    print("=== Phase 0 Round-Trip Test ===")
    print(f"Synthesizing /ɑ/ at F0={F0} Hz, formants={FORMANTS}, duration={DURATION}s")

    # Synthesize
    signal = synthesize_vowel(F0, FORMANTS, DURATION, SR)
    sf.write(OUTPUT, signal, SR)
    print(f"Saved to {OUTPUT}")

    # Measure
    print("\nMeasuring...")
    f0_result = measure_f0(signal, SR)
    formant_result = measure_formants(signal, SR)
    hnr_result = measure_harmonicity(signal, SR)
    js_result = measure_jitter_shimmer(signal, SR)
    tilt_result = measure_spectral_tilt(signal, SR)

    # Report
    print("\n--- Measured vs. Target ---")
    print(f"F0: target={F0} Hz, measured median={f0_result['median']} Hz (p5={f0_result['p5']}, p95={f0_result['p95']})")
    for f_name, target in FORMANTS.items():
        meas = formant_result[f_name]["median"]
        err_pct = abs(meas - target) / target * 100 if meas else float('inf')
        print(f"{f_name}: target={target} Hz, measured={meas} Hz, error={err_pct:.1f}%")
    print(f"HNR: {hnr_result['median']} dB")
    print(f"Jitter: {js_result['jitter_local_pct']}%")
    print(f"Shimmer: {js_result['shimmer_local_pct']}%")
    print(f"Tilt: {tilt_result['tilt_db_per_octave']} dB/oct")

    # Gate 0 check
    print("\n--- Gate 0 Check ---")
    passed = True

    # F0 check
    f0_err = abs(f0_result["median"] - F0)
    f0_ok = f0_err <= 3.0
    print(f"F0: error={f0_err:.1f} Hz (tolerance ±3 Hz) → {'PASS' if f0_ok else 'FAIL'}")
    passed = passed and f0_ok

    # Formant checks
    for f_name, target in FORMANTS.items():
        meas = formant_result[f_name]["median"]
        if meas is None:
            print(f"{f_name}: no measurement → FAIL")
            passed = False
            continue
        err_pct = abs(meas - target) / target * 100
        ok = err_pct <= 5.0
        print(f"{f_name}: error={err_pct:.1f}% (tolerance ±5%) → {'PASS' if ok else 'FAIL'}")
        passed = passed and ok

    print(f"\n{'='*40}")
    print(f"Gate 0: {'PASS' if passed else 'FAIL'}")
    print(f"{'='*40}")

    # Save results
    results = {
        "test": "Phase 0 Round-Trip",
        "target": {"F0": F0, "formants": FORMANTS},
        "measured": {
            "f0": f0_result,
            "formants": formant_result,
            "hnr": hnr_result,
            "jitter_shimmer": js_result,
            "tilt": tilt_result,
        },
        "gate0_passed": passed,
    }
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "round_trip_results.json")
    with open(out_path, "w") as fh:
        json.dump(results, fh, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
