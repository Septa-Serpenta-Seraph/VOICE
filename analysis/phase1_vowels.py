#!/usr/bin/env python3
"""
Phase 1 — Vowel Synthesis

Synthesizes all 12 vowels from the §5.2 grid, measures each with the
corrected harness, and reports Gate 0 results.

Updated for Round 5: F3 anchor shifted from 2300 → 2770 Hz.
Grid F3 values shifted +420 Hz to reflect new anchor.

Usage:
    /mnt/data/pocket-tts-venv/bin/python phase1_vowels.py
"""

import numpy as np
import soundfile as sf
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_voice import measure_f0, measure_formants, measure_harmonicity, measure_spectral_tilt
from round_trip_test import synthesize_vowel

# ── Vowel grid (§5.2, updated F3 anchor: 2300 → 2770, shift +420) ─────────
# Original F3 values shifted +420 to reflect new anchor.
# F4 adjusted to ensure F4 > F3 (formant ordering).
# Values are starting points for ear-tuning.
VOWEL_GRID = {
    "i":  {"F1": 300,  "F2": 2350, "F3": 3420, "F4": 3820},
    "ɪ":  {"F1": 430,  "F2": 1900, "F3": 3120, "F4": 3520},
    "e":  {"F1": 550,  "F2": 1900, "F3": 3020, "F4": 3420},
    "ɛ":  {"F1": 650,  "F2": 1750, "F3": 2970, "F4": 3370},
    "æ":  {"F1": 850,  "F2": 1650, "F3": 2920, "F4": 3320},
    "ɑ":  {"F1": 800,  "F2": 1150, "F3": 2820, "F4": 3220},
    "ʌ":  {"F1": 620,  "F2": 1250, "F3": 2770, "F4": 3170},
    "ɔ":  {"F1": 550,  "F2": 950,  "F3": 2770, "F4": 3170},
    "o":  {"F1": 450,  "F2": 900,  "F3": 2720, "F4": 3120},
    "ʊ":  {"F1": 430,  "F2": 1050, "F3": 2720, "F4": 3120},
    "u":  {"F1": 350,  "F2": 800,  "F3": 2670, "F4": 3070},
    "ə":  {"F1": 450,  "F2": 1500, "F3": 2720, "F4": 3120},
}

F0 = 190.0
DURATION = 1.0
SR = 48000
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phase1_vowels")
os.makedirs(OUT_DIR, exist_ok=True)


def run_gate0(target_f0, target_formants, measured_f0, measured_formants):
    """Check Gate 0 tolerances."""
    results = {}
    # F0
    f0_err = abs(measured_f0 - target_f0)
    results["F0"] = {"error": round(f0_err, 1), "tolerance": 3.0, "pass": f0_err <= 3.0}
    # Formants
    for fn, target in target_formants.items():
        meas = measured_formants[fn]["median"]
        if meas is None:
            results[fn] = {"error": None, "tolerance": 5.0, "pass": False}
            continue
        err_pct = abs(meas - target) / target * 100
        results[fn] = {"error": round(err_pct, 1), "tolerance": 5.0, "pass": err_pct <= 5.0}
    return results, all(r["pass"] for r in results.values())


def main():
    print("=== Phase 1: Vowel Synthesis ===")
    print(f"F0: {F0} Hz, Duration: {DURATION}s, SR: {SR} Hz")
    print(f"Vowels: {len(VOWEL_GRID)}\n")

    all_results = {}
    all_pass = True

    for vowel, formants in VOWEL_GRID.items():
        print(f"--- /{vowel}/ ---")
        print(f"  Target: F1={formants['F1']}, F2={formants['F2']}, F3={formants['F3']}, F4={formants['F4']}")

        # Synthesize
        signal = synthesize_vowel(F0, formants, DURATION, SR)
        wav_path = os.path.join(OUT_DIR, f"vowel_{vowel}.wav")
        sf.write(wav_path, signal, SR)

        # Measure
        f0_res = measure_f0(signal, SR)
        fm_res = measure_formants(signal, SR)
        hnr_res = measure_harmonicity(signal, SR)
        tilt_res = measure_spectral_tilt(signal, SR)

        measured_f0 = f0_res["median"]
        gate_results, passed = run_gate0(F0, formants, measured_f0, fm_res)

        print(f"  Measured: F0={measured_f0} Hz, F1={fm_res['F1']['median']}, F2={fm_res['F2']['median']}, F3={fm_res['F3']['median']}, F4={fm_res['F4']['median']}")
        print(f"  Gate 0: {'PASS' if passed else 'FAIL'}")
        for fn, r in gate_results.items():
            status = "✓" if r["pass"] else "✗"
            err = f"{r['error']}" if r["error"] is not None else "N/A"
            print(f"    {fn}: error={err} (tol ±{r['tolerance']}) {status}")

        all_results[vowel] = {
            "target": {"F0": F0, "formants": formants},
            "measured": {
                "f0": f0_res,
                "formants": fm_res,
                "hnr": hnr_res,
                "tilt": tilt_res,
            },
            "gate0": gate_results,
            "passed": passed,
        }
        all_pass = all_pass and passed

    # Summary
    print("\n" + "=" * 60)
    print("PHASE 1 SUMMARY")
    print("=" * 60)
    n_pass = sum(1 for v in all_results.values() if v["passed"])
    print(f"Vowels: {len(all_results)}, Passed: {n_pass}, Failed: {len(all_results) - n_pass}")
    print()
    for vowel, r in all_results.items():
        status = "PASS" if r["passed"] else "FAIL"
        f0e = r["gate0"]["F0"]["error"]
        f1e = r["gate0"]["F1"]["error"]
        f2e = r["gate0"]["F2"]["error"]
        f3e = r["gate0"]["F3"]["error"]
        f4e = r["gate0"]["F4"]["error"]
        print(f"  /{vowel}/: {status} (F0={f0e}Hz, F1={f1e}%, F2={f2e}%, F3={f3e}%, F4={f4e}%)")

    print(f"\nOverall Phase 1 Gate 0: {'PASS' if all_pass else 'FAIL'}")

    # Save results
    out_path = os.path.join(OUT_DIR, "phase1_results.json")
    with open(out_path, "w") as fh:
        json.dump({"F0": F0, "vowels": all_results, "all_pass": all_pass}, fh, indent=2)
    print(f"Results saved to {out_path}")
    print(f"Audio files saved to {OUT_DIR}/")


if __name__ == "__main__":
    main()
