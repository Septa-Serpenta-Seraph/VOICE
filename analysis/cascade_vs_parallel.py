#!/usr/bin/env python3
"""
VOICE — Cascade vs Parallel resonator bank comparison.

Proper comparison with per-formant gains and genome bandwidths.
Measures formant recovery for both synthesis methods.

Usage:
    python cascade_vs_parallel.py --duration 1.5 --seed 7
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


def load_genome(path):
    with open(path) as fh:
        return yaml.safe_load(fh)


def synthesize_parallel(f0, formants, duration, sr, source, bandwidths=None):
    """Parallel resonator bank — each formant independent, outputs summed."""
    n_samples = int(duration * sr)
    source = source[:n_samples]

    output = np.zeros(n_samples)
    for name, f_freq in formants.items():
        bw = bandwidths[name] if bandwidths and name in bandwidths else f_freq * 0.1
        w0 = 2 * np.pi * f_freq / sr
        r = np.exp(-np.pi * bw / sr)
        a = [1.0, -2 * r * np.cos(w0), r ** 2]
        resonator_out = lfilter([1.0], a, source)
        output += resonator_out

    output = np.diff(output, prepend=output[0])
    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.5
    return output


def synthesize_cascade(f0, formants, duration, sr, source, bandwidths=None, gains=None):
    """Cascade resonator bank — formants in series, each filters the previous.

    Each stage: output[n] = resonator(output_prev, f_freq, bw)
    With per-formant gains to compensate for cascade interaction.
    """
    n_samples = int(duration * sr)
    source = source[:n_samples]

    # Default gains: compensate for cascade rolloff (higher formants need more gain)
    if gains is None:
        gains = {"F1": 1.0, "F2": 1.0, "F3": 1.2, "F4": 1.5}

    output = source.copy()
    for name, f_freq in formants.items():
        bw = bandwidths[name] if bandwidths and name in bandwidths else f_freq * 0.1
        w0 = 2 * np.pi * f_freq / sr
        r = np.exp(-np.pi * bw / sr)
        a = [1.0, -2 * r * np.cos(w0), r ** 2]
        b = [gains.get(name, 1.0)]
        output = lfilter(b, a, output)

    output = np.diff(output, prepend=output[0])
    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.5
    return output


def make_source(genome, f0, duration, source_kind, rng):
    """Generate source signal."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from analysis.phase1_synth import make_source as ms
    return ms(genome, f0, duration, source_kind, rng)


def measure_formants(signal, sr, targets):
    """Measure formants using synthetic mode."""
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from synthetic_measure import measure_formants_synthetic
    return measure_formants_synthetic(signal, sr, targets)


def compare(genome, vowels, f0, duration, source_kind, seed, sr=SR):
    """Run cascade vs parallel comparison."""
    rng_parallel = np.random.default_rng(seed)
    rng_cascade = np.random.default_rng(seed)  # same seed for fair comparison

    anchor = genome["filter"]["neutral_anchor"]
    bandwidths = {k: anchor[k]["bw"] for k in ["F1", "F2", "F3", "F4"]
                  if k in anchor and isinstance(anchor[k], dict)}

    results = {"parallel": {}, "cascade": {}}

    for vowel in vowels:
        grid = genome["vowel_grid"][vowel]
        f1, f2, f3 = grid[0], grid[1], grid[2]
        f4 = anchor["F4"]["hz"]
        formants = {"F1": f1, "F2": f2, "F3": f3, "F4": f4}
        targets = formants.copy()

        # Parallel
        source_p = make_source(genome, f0, duration, source_kind, rng_parallel)
        sig_p = synthesize_parallel(f0, formants, duration, sr, source_p, bandwidths=bandwidths)
        meas_p = measure_formants(sig_p[int(0.25*sr):], sr, targets)

        # Cascade
        source_c = make_source(genome, f0, duration, source_kind, rng_cascade)
        sig_c = synthesize_cascade(f0, formants, duration, sr, source_c, bandwidths=bandwidths)
        meas_c = measure_formants(sig_c[int(0.25*sr):], sr, targets)

        # Compute errors
        def errors(meas, targets):
            errs = {}
            for k in targets:
                if k in meas and "error_pct" in meas[k]:
                    errs[k] = meas[k]["error_pct"]
                else:
                    errs[k] = 100.0
            return errs

        results["parallel"][vowel] = {
            "errors": errors(meas_p, targets),
            "max_error": max(errors(meas_p, targets).values()) if errors(meas_p, targets) else 100,
        }
        results["cascade"][vowel] = {
            "errors": errors(meas_c, targets),
            "max_error": max(errors(meas_c, targets).values()) if errors(meas_c, targets) else 100,
        }

    # Summary
    for method in ["parallel", "cascade"]:
        all_errs = []
        for v in vowels:
            all_errs.extend(results[method][v]["errors"].values())
        results[method]["_summary"] = {
            "mean_error": round(float(np.mean(all_errs)), 2),
            "max_error": round(float(np.max(all_errs)), 2),
            "n_vowels_passing": sum(1 for v in vowels if results[method][v]["max_error"] < 5.0),
        }

    return results


def main():
    parser = argparse.ArgumentParser(description="Cascade vs Parallel comparison")
    parser.add_argument("--genome", default="genome/voice_genome.yaml")
    parser.add_argument("--duration", type=float, default=1.5)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--source", choices=["simple", "lf"], default="simple")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    genome = load_genome(args.genome)
    f0 = 190.0
    vowels = ["i", "ɪ", "e", "ɛ", "æ", "ɑ", "ʌ", "ɔ", "o", "ʊ", "u", "ə"]

    results = compare(genome, vowels, f0, args.duration, args.source, args.seed)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("Cascade vs Parallel — Formant Recovery Comparison")
        print("=" * 70)
        print(f"{'Method':<12} {'Mean err':>10} {'Max err':>10} {'Passing':>10}")
        print("-" * 70)
        for method in ["parallel", "cascade"]:
            s = results[method]["_summary"]
            print(f"{method:<12} {s['mean_error']:>9.2f}% {s['max_error']:>9.2f}% "
                  f"{s['n_vowels_passing']:>8}/12")

        print()
        print("Per-vowel max error:")
        print(f"{'Vowel':<6} {'Parallel':>10} {'Cascade':>10}")
        print("-" * 30)
        for v in vowels:
            p = results["parallel"][v]["max_error"]
            c = results["cascade"][v]["max_error"]
            print(f"{v:<6} {p:>9.2f}% {c:>9.2f}%")

        print()
        p_sum = results["parallel"]["_summary"]
        c_sum = results["cascade"]["_summary"]
        if p_sum["mean_error"] < c_sum["mean_error"]:
            print("Winner: PARALLEL (lower mean error)")
        elif c_sum["mean_error"] < p_sum["mean_error"]:
            print("Winner: CASCADE (lower mean error)")
        else:
            print("Tie")


if __name__ == "__main__":
    main()