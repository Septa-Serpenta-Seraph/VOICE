#!/usr/bin/env python3
"""
VOICE — Filter-based Gate 0 measurement (Round 9, Zarza's suggestion).

Instead of hunting spectral peaks in the rendered signal (which can't
fail because the window is ±5% of the target), measure the frequency
response of the resonator bank itself using scipy.signal.freqz.

Harmonics and F0 drop out of the measurement entirely. The gate can
actually fail: a filter with wrong center frequencies won't produce
peaks at the right places.

Usage:
    python filter_gate0.py --demo     # test with default formants
    python filter_gate0.py --test     # negative control + positive control
"""

import argparse
import json
import os
import sys

import numpy as np
from scipy import signal as scipy_signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Genome bandwidths from voice_genome.yaml
GENOME_BANDWIDTHS = {"F1": 80, "F2": 100, "F3": 120, "F4": 150}
GENOME_FORMANTS = {"F1": 450, "F2": 1500, "F3": 2770, "F4": 3100}


def resonator_coefficients(f_freq, sr, bw=None):
    """Compute IIR resonator coefficients for a formant at f_freq."""
    if bw is None:
        bw = f_freq * 0.1
    w0 = 2 * np.pi * f_freq / sr
    r = np.exp(-np.pi * bw / sr)
    a = [1.0, -2 * r * np.cos(w0), r ** 2]
    b = [1.0]
    return b, a


def measure_filter_peaks(formants, sr=48000, n_points=8192, bandwidths=None):
    """Measure formant peaks from the filter's frequency response.

    formants: dict of {name: freq} or {name: (freq, bw)}
    bandwidths: optional dict of {name: bw}
    """
    freq_map = {}
    bw_map = {}
    for name, val in (formants.items() if isinstance(formants, dict) else enumerate(formants)):
        if isinstance(val, (tuple, list)):
            freq_map[name] = val[0]
            bw_map[name] = val[1]
        else:
            freq_map[name] = val
            bw_map[name] = None

    if bandwidths:
        for name, bw in bandwidths.items():
            bw_map[name] = bw

    # Combined frequency response
    w, h_combined = scipy_signal.freqz([1.0], [1.0], worN=n_points, fs=sr)
    h_combined = np.zeros(n_points, dtype=complex)

    for name, f_freq in freq_map.items():
        bw = bw_map.get(name)
        if bw is None:
            bw = f_freq * 0.1
        b, a = resonator_coefficients(f_freq, sr, bw=bw)
        w, h = scipy_signal.freqz(b, a, worN=n_points, fs=sr)
        h_combined += h

    freqs = w
    mag_db = 20 * np.log10(np.abs(h_combined) + 1e-20)

    # Find peaks
    peaks, properties = scipy_signal.find_peaks(mag_db, prominence=1.0, distance=5)

    peak_freqs = freqs[peaks]
    peak_mags = mag_db[peaks]

    # Match peaks to nearest formant targets
    measured = {}
    target_names = list(freq_map.keys())
    targets = list(freq_map.values())

    for name, target in zip(target_names, targets):
        if len(peak_freqs) > 0:
            idx = np.argmin(np.abs(peak_freqs - target))
            measured[name] = {
                "target": target,
                "measured": round(float(peak_freqs[idx]), 1),
                "error_pct": round(abs(peak_freqs[idx] - target) / target * 100, 2),
                "mag_db": round(float(peak_mags[idx]), 1),
                "bw": bw_map.get(name),
            }
        else:
            measured[name] = {
                "target": target,
                "measured": None,
                "error_pct": 100.0,
                "mag_db": None,
                "bw": bw_map.get(name),
            }

    return measured, peak_freqs, peak_mags


def gate0_filter(measured, tolerance_pct=5.0):
    """Gate 0 using filter measurement."""
    passed = True
    notes = []

    for name, m in measured.items():
        if m["measured"] is None:
            passed = False
            notes.append(f"{name}: no peak found")
            continue
        if m["error_pct"] > tolerance_pct:
            passed = False
            notes.append(f"{name}: {m['measured']} vs {m['target']} "
                         f"({m['error_pct']}% > {tolerance_pct}%)")

    return passed, notes


def negative_control_filter(sr=48000):
    """Negative control: wrong filter must fail.

    The wrong filter has different center frequencies. We measure its
    response and compare against the CORRECT targets — the gate should
    detect that the peaks don't match.
    """
    correct = {"F1": 450, "F2": 1500, "F3": 2770, "F4": 3100}
    wrong = {"F1": 540, "F2": 1800, "F3": 3324, "F4": 3720}

    bw = GENOME_BANDWIDTHS

    # Measure the WRONG filter's response
    measured_wrong, peaks_wrong, _ = measure_filter_peaks(wrong, sr=sr, bandwidths=bw)

    # But compare against CORRECT targets
    # Re-measure: find nearest peak to each CORRECT target
    measured_against_correct = {}
    for name, target in correct.items():
        if len(peaks_wrong) > 0:
            idx = np.argmin(np.abs(peaks_wrong - target))
            measured_against_correct[name] = {
                "target": target,
                "measured": round(float(peaks_wrong[idx]), 1),
                "error_pct": round(abs(peaks_wrong[idx] - target) / target * 100, 2),
                "mag_db": None,
                "bw": bw.get(name),
            }
        else:
            measured_against_correct[name] = {
                "target": target,
                "measured": None,
                "error_pct": 100.0,
                "mag_db": None,
                "bw": bw.get(name),
            }

    # Correct filter measured against correct targets
    measured_correct, _, _ = measure_filter_peaks(correct, sr=sr, bandwidths=bw)

    _, notes_correct = gate0_filter(measured_correct)
    _, notes_wrong = gate0_filter(measured_against_correct)

    passes_correct = len(notes_correct) == 0
    fails_wrong = len(notes_wrong) > 0

    return {
        "passes_correct": passes_correct,
        "fails_wrong": fails_wrong,
        "negative_control_passes": passes_correct and fails_wrong,
        "correct_notes": notes_correct,
        "wrong_notes": notes_wrong,
        "measured_correct": measured_correct,
        "measured_wrong_against_correct": measured_against_correct,
    }


def demo(sr=48000):
    """Demo: measure filter peaks for genome formants."""
    formants = GENOME_FORMANTS
    measured, peak_freqs, peak_mags = measure_filter_peaks(
        formants, sr=sr, bandwidths=GENOME_BANDWIDTHS)

    print("Filter-based Gate 0 Measurement (genome bandwidths)")
    print("=" * 60)
    print(f"{'Formant':>8} {'Target':>8} {'Measured':>10} {'Error':>8} {'Mag (dB)':>10} {'BW':>6}")
    print("-" * 60)
    for name, m in measured.items():
        print(f"{name:>8} {m['target']:>8} {m['measured']:>10} "
              f"{m['error_pct']:>7.2f}% {m['mag_db']:>9.1f} {m['bw']:>6}")

    passed, notes = gate0_filter(measured)
    print(f"\nGate 0: {'PASS' if passed else 'FAIL'}")
    if notes:
        for n in notes:
            print(f"  {n}")

    print(f"\nAll peaks found: {peak_freqs.round(1)}")

    # Negative control
    print("\nNegative control (20% off targets):")
    nc = negative_control_filter(sr=sr)
    print(f"  Correct filter passes: {nc['passes_correct']}")
    print(f"  Wrong filter fails: {nc['fails_wrong']}")
    print(f"  Negative control: {'PASS' if nc['negative_control_passes'] else 'FAIL'}")
    if nc["wrong_notes"]:
        print(f"  Wrong notes: {nc['wrong_notes']}")


def main():
    parser = argparse.ArgumentParser(description="Filter-based Gate 0")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--test", action="store_true", help="Run negative control test")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--sr", type=int, default=48000)
    args = parser.parse_args()

    if args.test:
        nc = negative_control_filter(sr=args.sr)
        if args.json:
            print(json.dumps(nc, indent=2, default=str))
        else:
            print(f"Negative control: {'PASS' if nc['negative_control_passes'] else 'FAIL'}")
            print(f"  Correct filter passes: {nc['passes_correct']}")
            print(f"  Wrong filter fails: {nc['fails_wrong']}")
            if nc["wrong_notes"]:
                print(f"  Wrong notes: {nc['wrong_notes']}")
        return

    demo(sr=args.sr)


if __name__ == "__main__":
    main()