#!/usr/bin/env python3
"""
Phase 0 Sensitivity Test — verify the harness notices perturbations.

Tests that the measurement harness detects:
  - F0 ±20 Hz (should measure ~±20 Hz difference)
  - F3 ±5% (should measure ~±5% difference)

This is the sensitivity that Gate 3's discrimination test stands on.

Usage:
    /mnt/data/pocket-tts-venv/bin/python sensitivity_test.py
"""

import numpy as np
import soundfile as sf
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_voice import measure_f0, measure_formants
from round_trip_test import synthesize_vowel

FORMANTS_BASE = {"F1": 800.0, "F2": 1150.0, "F3": 2400.0, "F4": 3100.0}
SR = 48000
DURATION = 1.0
OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def measure(signal):
    f0 = measure_f0(signal, SR)
    fm = measure_formants(signal, SR)
    return f0["median"], fm["F3"]["median"]


def main():
    print("=== Phase 0 Sensitivity Test ===\n")

    # Baseline
    sig_base = synthesize_vowel(190.0, FORMANTS_BASE, DURATION, SR)
    f0_base, f3_base = measure(sig_base)
    print(f"Baseline: F0={f0_base} Hz, F3={f3_base} Hz\n")

    # F0 perturbations
    print("--- F0 sensitivity (±20 Hz) ---")
    for delta in [-20, -10, 0, 10, 20]:
        sig = synthesize_vowel(190.0 + delta, FORMANTS_BASE, DURATION, SR)
        f0, f3 = measure(sig)
        print(f"  F0 target={190+delta:6.1f} Hz → measured={f0:6.1f} Hz (delta from baseline: {f0-f0_base:+.1f})")

    # F3 perturbations
    print("\n--- F3 sensitivity (±5%) ---")
    for pct in [-5, -2.5, 0, 2.5, 5]:
        f3_target = FORMANTS_BASE["F3"] * (1 + pct/100)
        fm = dict(FORMANTS_BASE)
        fm["F3"] = f3_target
        sig = synthesize_vowel(190.0, fm, DURATION, SR)
        f0, f3 = measure(sig)
        print(f"  F3 target={f3_target:7.1f} Hz ({pct:+.1f}%) → measured={f3:7.1f} Hz (delta from baseline: {f3-f3_base:+.1f})")

    print("\n--- Verdict ---")
    # Check that ±20 Hz F0 is detectable
    sig_plus = synthesize_vowel(210.0, FORMANTS_BASE, DURATION, SR)
    sig_minus = synthesize_vowel(170.0, FORMANTS_BASE, DURATION, SR)
    f0_plus, _ = measure(sig_plus)
    f0_minus, _ = measure(sig_minus)
    f0_detectable = abs(f0_plus - f0_minus) > 30  # should be ~40 Hz
    print(f"F0 ±20 Hz detectable: {f0_detectable} (measured spread: {abs(f0_plus - f0_minus):.1f} Hz)")

    # Check that ±5% F3 is detectable
    fm_plus = dict(FORMANTS_BASE)
    fm_plus["F3"] = FORMANTS_BASE["F3"] * 1.05
    fm_minus = dict(FORMANTS_BASE)
    fm_minus["F3"] = FORMANTS_BASE["F3"] * 0.95
    sig_f3plus = synthesize_vowel(190.0, fm_plus, DURATION, SR)
    sig_f3minus = synthesize_vowel(190.0, fm_minus, DURATION, SR)
    _, f3_plus = measure(sig_f3plus)
    _, f3_minus = measure(sig_f3minus)
    f3_detectable = abs(f3_plus - f3_minus) > 100  # should be ~240 Hz
    print(f"F3 ±5% detectable: {f3_detectable} (measured spread: {abs(f3_plus - f3_minus):.1f} Hz)")

    passed = f0_detectable and f3_detectable
    print(f"\nSensitivity: {'PASS' if passed else 'FAIL'}")


if __name__ == "__main__":
    main()
