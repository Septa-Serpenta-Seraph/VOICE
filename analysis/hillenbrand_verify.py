#!/usr/bin/env python3
"""
VOICE — Hillenbrand (h95) verification for neutral anchor F2.

Compares genome neutral anchor values against Hillenbrand et al. (1995)
female speaker data. Verifies F2 = 1500 Hz against population statistics.

Usage:
    python hillenbrand_verify.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Genome neutral anchor
GENOME_F1 = 450
GENOME_F2 = 1500
GENOME_F3 = 2770
GENOME_F4 = 3100


def parse_h95(path):
    """Parse vowdata.dat from Hillenbrand et al. (1995)."""
    data = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 7 and len(parts[0]) >= 5 and parts[0][0] in "mwbg" and parts[0][3:5].isalpha():
                data.append(parts)
    return data


def verify(data_path):
    data = parse_h95(data_path)
    women = [d for d in data if d[0].startswith("w")]

    # Overall medians
    f1_all = [float(d[3]) for d in women if float(d[3]) > 0]
    f2_all = [float(d[4]) for d in women if float(d[4]) > 0]
    f3_all = [float(d[5]) for d in women if float(d[5]) > 0]

    # Per-vowel medians
    from collections import defaultdict
    vowel_stats = defaultdict(lambda: {"f1": [], "f2": [], "f3": []})
    for d in women:
        v = d[0][3:5]
        if float(d[3]) > 0:
            vowel_stats[v]["f1"].append(float(d[3]))
        if float(d[4]) > 0:
            vowel_stats[v]["f2"].append(float(d[4]))
        if float(d[5]) > 0:
            vowel_stats[v]["f3"].append(float(d[5]))

    results = {
        "n_women": len(set(d[0][:3] for d in women)),
        "n_tokens": len(women),
        "overall": {
            "F1_median": round(float(np.median(f1_all)), 1),
            "F2_median": round(float(np.median(f2_all)), 1),
            "F3_median": round(float(np.median(f3_all)), 1),
        },
        "genome_anchor": {
            "F1": GENOME_F1,
            "F2": GENOME_F2,
            "F3": GENOME_F3,
            "F4": GENOME_F4,
        },
        "deviation_pct": {
            "F1": round(abs(GENOME_F1 - np.median(f1_all)) / np.median(f1_all) * 100, 1),
            "F2": round(abs(GENOME_F2 - np.median(f2_all)) / np.median(f2_all) * 100, 1),
            "F3": round(abs(GENOME_F3 - np.median(f3_all)) / np.median(f3_all) * 100, 1),
        },
        "per_vowel_f2": {},
    }

    for v in sorted(vowel_stats):
        vals = vowel_stats[v]["f2"]
        if vals:
            results["per_vowel_f2"][v] = {
                "n": len(vals),
                "median": round(float(np.median(vals)), 1),
                "mean": round(float(np.mean(vals)), 1),
            }

    # Closest vowel to genome F2
    closest = min(vowel_stats, key=lambda v: abs(np.median(vowel_stats[v]["f2"]) - GENOME_F2))
    results["closest_vowel_to_F2"] = {
        "vowel": closest,
        "median_F2": round(float(np.median(vowel_stats[closest]["f2"])), 1),
        "deviation_pct": round(abs(np.median(vowel_stats[closest]["f2"]) - GENOME_F2) / GENOME_F2 * 100, 1),
    }

    return results


def main():
    data_path = "/tmp/h95/vowdata.dat"
    if not os.path.exists(data_path):
        print("ERROR: vowdata.dat not found. Download h95-alldata.zip from GitHub.")
        sys.exit(1)

    results = verify(data_path)

    print("Hillenbrand (h95) Verification — Female Speakers")
    print("=" * 60)
    print(f"Speakers: {results['n_women']} women, {results['n_tokens']} tokens")
    print()
    print("Overall medians (all vowels, steady state):")
    print(f"  F1: {results['overall']['F1_median']} Hz  (genome: {GENOME_F1}, dev: {results['deviation_pct']['F1']}%)")
    print(f"  F2: {results['overall']['F2_median']} Hz  (genome: {GENOME_F2}, dev: {results['deviation_pct']['F2']}%)")
    print(f"  F3: {results['overall']['F3_median']} Hz  (genome: {GENOME_F3}, dev: {results['deviation_pct']['F3']}%)")
    print()
    print(f"Closest vowel to genome F2 ({GENOME_F2} Hz):")
    print(f"  {results['closest_vowel_to_F2']['vowel']}: median F2 = {results['closest_vowel_to_F2']['median_F2']} Hz "
          f"(deviation: {results['closest_vowel_to_F2']['deviation_pct']}%)")
    print()
    print("Per-vowel F2 (women):")
    for v, stats in results["per_vowel_f2"].items():
        marker = " <-- closest" if v == results["closest_vowel_to_F2"]["vowel"] else ""
        print(f"  {v}: n={stats['n']}, median={stats['median']}, mean={stats['mean']}{marker}")
    print()
    print("Verdict:")
    f2_dev = results["deviation_pct"]["F2"]
    if f2_dev < 10:
        print(f"  F2 = {GENOME_F2} Hz is within {f2_dev}% of population median ({results['overall']['F2_median']} Hz).")
        print("  VALIDATED — genome neutral anchor F2 is consistent with Hillenbrand data.")
    else:
        print(f"  F2 = {GENOME_F2} Hz deviates {f2_dev}% from population median. Review needed.")

    # Save JSON
    out_path = os.path.join(os.path.dirname(__file__), "..", "renders", "hillenbrand_verify.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    import json
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nReport: {out_path}")


if __name__ == "__main__":
    main()