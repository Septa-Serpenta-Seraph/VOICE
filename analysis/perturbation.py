#!/usr/bin/env python3
"""
VOICE — Perturbation round-trip (oldest open item, now closing)
==============================================================
Implement Round 2 perturbation structure in the glottal path:
slow drift (0.3-0.7 Hz wander) + cycle-to-cycle components.
NOT independent per-cycle noise (that sounds like buzz).

Genome targets (sustained vowels):
  jitter_local_pct: 0.7% (range 0.5-0.9%)
  shimmer_local_pct: 4.0% (range 3.0-5.0%)
  structure: slow_drift_plus_cycle

Measurement: Praat PointProcess on a dedicated steady render,
onsets trimmed. Known values in → measured values out.

Usage:
  python perturbation.py --demo     # synthesize with perturbation
  python perturbation.py --test      # round-trip test
"""

import argparse
import json
import os
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 48000

# Genome perturbation targets
JITTER_TARGET = 0.7   # % (local jitter on sustained vowels)
SHIMMER_TARGET = 4.0  # % (local shimmer on sustained vowels)
JITTER_RANGE = (0.5, 0.9)
SHIMMER_RANGE = (3.0, 5.0)


def perturbed_pulse_train(f0, duration, sr, jitter_pct=JITTER_TARGET,
                          shimmer_pct=SHIMMER_TARGET, seed=42, trim_onset=0.25):
    """Generate a perturbed glottal pulse train with structured jitter+shimmer.

    Structure: slow_drift_plus_cycle (Round 2 specification).
    - Slow drift: 0.3-0.7 Hz amplitude wander (not per-cycle)
    - Cycle jitter: small cycle-to-cycle pitch variation (0.7% target)
    - Cycle shimmer: small cycle-to-cycle amplitude variation (4.0% target)

    NOT independent per-cycle noise — that sounds like buzz.
    The slow drift modulates the cycle parameters, creating natural
    "aliveness" without buzziness.

    Returns: (signal, onset_trim_samples)
    """
    rng = np.random.default_rng(seed)
    n_samples = int(duration * sr)
    onset_trim = int(trim_onset * sr)

    # Slow drift parameters (0.3-0.7 Hz)
    drift_freq = 0.5  # Hz
    drift_phase = rng.uniform(0, 2 * np.pi)

    # Generate pulse train with perturbation
    signal = np.zeros(n_samples)
    pos = 0
    cycle_count = 0

    # Pre-compute slow drift envelope
    t_all = np.arange(n_samples) / sr
    drift_envelope = 1.0 + 0.02 * np.sin(2 * np.pi * drift_freq * t_all + drift_phase)

    while pos < n_samples:
        # Cycle period with jitter
        # Slow drift modulates the jitter
        drift_mod = drift_envelope[pos] if pos < len(drift_envelope) else 1.0

        # Cycle jitter: base + slow drift modulation
        base_jitter = rng.normal(0, jitter_pct / 100.0 / np.sqrt(2))
        cycle_jitter = base_jitter * drift_mod
        period_samples = int(round(sr / f0 * (1.0 + cycle_jitter)))
        period_samples = max(period_samples, 8)

        # Cycle shimmer: base + slow drift modulation
        base_shimmer = rng.normal(0, shimmer_pct / 100.0 / np.sqrt(2))
        cycle_shimmer = base_shimmer * drift_mod
        amplitude = 1.0 + cycle_shimmer

        # Place pulse
        if pos < n_samples:
            signal[pos] = amplitude

        pos += period_samples
        cycle_count += 1

    # Apply glottal pulse shape (one-pole smoothing)
    signal = lfilter([1.0], [1.0, -0.95], signal)

    # Apply slow amplitude wander (the "breathing" quality)
    wander = 1.0 + 0.01 * np.sin(2 * np.pi * 0.3 * t_all + drift_phase)
    signal = signal * wander

    return signal, onset_trim


def synthesize_perturbed_vowel(vowel, genome, f0, duration, sr=SR, seed=42,
                                jitter_pct=JITTER_TARGET, shimmer_pct=SHIMMER_TARGET):
    """Synthesize a vowel with perturbation, ready for Praat measurement.

    Returns: (signal, onset_trim_samples)
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from phase1_synth import render_vowel

    # Generate perturbed source
    source, onset_trim = perturbed_pulse_train(
        f0, duration, sr, jitter_pct=jitter_pct, shimmer_pct=shimmer_pct, seed=seed
    )

    # Get formants from genome
    grid = genome["vowel_grid"][vowel]
    anchor = genome["filter"]["neutral_anchor"]
    formants = {
        "F1": grid[0],
        "F2": grid[1],
        "F3": grid[2],
        "F4": anchor["F4"]["hz"],
    }

    # Apply formant filters (parallel resonator bank)
    n_samples = len(source)
    output = np.zeros(n_samples)
    for f_freq in formants.values():
        w0 = 2 * np.pi * f_freq / sr
        bw = f_freq * 0.1
        r = np.exp(-np.pi * bw / sr)
        a = [1.0, -2 * r * np.cos(w0), r ** 2]
        from scipy.signal import lfilter as lf
        resonator_out = lf([1.0], a, source)
        output += resonator_out

    # Radiation
    output = np.diff(output, prepend=output[0])
    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.5

    return output, onset_trim


def measure_jitter_shimmer_praat(signal, sr, f0=190.0):
    """Measure jitter and shimmer using Praat via parselmouth.

    Returns: (jitter_local_pct, shimmer_local_pct, n_cycles)
    """
    import parselmouth
    from parselmouth.praat import call

    # Create Sound object
    snd = parselmouth.Sound(signal, sampling_frequency=sr)

    # Create PointProcess (periodic, cc)
    pp = call(snd, "To PointProcess (periodic, cc)", f0 * 0.8, f0 * 1.2)

    # Measure jitter (local) — PointProcess only
    jitter = call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
    # Measure shimmer (local) — needs PointProcess + Sound
    shimmer = call([pp, snd], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)

    n_cycles = call(pp, "Get number of points")

    return {
        "jitter_local_pct": round(jitter * 100, 3) if jitter is not None else None,
        "shimmer_local_pct": round(shimmer * 100, 3) if shimmer is not None else None,
        "n_cycles": int(n_cycles) if n_cycles is not None else 0,
    }


def round_trip_test(genome, f0=190.0, duration=3.0, sr=SR, seed=42):
    """Round-trip test: synthesize with known jitter/shimmer, measure back.

    Uses a sustained vowel render with onset trimmed.
    """
    import yaml

    # Test with known values
    known_jitter = JITTER_TARGET
    known_shimmer = SHIMMER_TARGET

    # Synthesize
    signal, onset_trim = synthesize_perturbed_vowel(
        "ɑ", genome, f0, duration, sr=sr, seed=seed,
        jitter_pct=known_jitter, shimmer_pct=known_shimmer
    )

    # Trim onset
    trimmed = signal[onset_trim:]

    # Measure with Praat
    result = measure_jitter_shimmer_praat(trimmed, sr, f0=f0)

    # Check recovery
    got_j = result["jitter_local_pct"]
    got_s = result["shimmer_local_pct"]

    recovered_j = (got_j is not None and
                   abs(got_j - known_jitter) < 0.3)
    recovered_s = (got_s is not None and
                   abs(got_s - known_shimmer) < 1.0)

    return {
        "known_jitter_pct": known_jitter,
        "measured_jitter_pct": got_j,
        "jitter_recovered": recovered_j,
        "known_shimmer_pct": known_shimmer,
        "measured_shimmer_pct": got_s,
        "shimmer_recovered": recovered_s,
        "n_cycles": result["n_cycles"],
        "round_trip_passed": recovered_j and recovered_s,
    }


def demo(sr=SR, duration=3.0, seed=42):
    """Demo: synthesize /ɑ/ with perturbation and save."""
    import yaml
    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    with open(genome_path) as f:
        genome = yaml.safe_load(f)

    f0 = 190.0
    signal, onset_trim = synthesize_perturbed_vowel(
        "ɑ", genome, f0, duration, sr=sr, seed=seed
    )

    # Save full and trimmed
    out_dir = os.path.join(os.path.dirname(__file__), "..", "renders")
    os.makedirs(out_dir, exist_ok=True)
    wavfile.write(os.path.join(out_dir, "vowel_ɑ_perturbed.wav"), sr,
                  (signal * 32767).astype(np.int16))
    wavfile.write(os.path.join(out_dir, "vowel_ɑ_perturbed_trimmed.wav"), sr,
                  (signal[onset_trim:] * 32767).astype(np.int16))

    # Measure
    result = measure_jitter_shimmer_praat(signal[onset_trim:], sr, f0=f0)
    print(f"Perturbed /ɑ/ (trimmed):")
    print(f"  Jitter: {result['jitter_local_pct']}% (target: {JITTER_TARGET}%)")
    print(f"  Shimmer: {result['shimmer_local_pct']}% (target: {SHIMMER_TARGET}%)")
    print(f"  Cycles: {result['n_cycles']}")
    print(f"  Saved: vowel_ɑ_perturbed.wav, vowel_ɑ_perturbed_trimmed.wav")

    return signal, result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VOICE perturbation")
    parser.add_argument("--demo", action="store_true",
                        help="Synthesize /ɑ/ with perturbation")
    parser.add_argument("--test", action="store_true",
                        help="Run round-trip test")
    parser.add_argument("--sr", type=int, default=SR)
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    import yaml
    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    with open(genome_path) as f:
        genome = yaml.safe_load(f)

    if args.demo:
        signal, result = demo(sr=args.sr, duration=args.duration, seed=args.seed)

    elif args.test:
        result = round_trip_test(genome, f0=190.0, duration=args.duration,
                                sr=args.sr, seed=args.seed)
        print(f"\nRound-trip test:")
        print(f"  Jitter: {result['known_jitter_pct']}% in → "
              f"{result['measured_jitter_pct']}% out "
              f"({'PASS' if result['jitter_recovered'] else 'FAIL'})")
        print(f"  Shimmer: {result['known_shimmer_pct']}% in → "
              f"{result['measured_shimmer_pct']}% out "
              f"({'PASS' if result['shimmer_recovered'] else 'FAIL'})")
        print(f"  Cycles: {result['n_cycles']}")
        print(f"  Overall: {'PASS' if result['round_trip_passed'] else 'FAIL'}")

        out = os.path.join(os.path.dirname(__file__), "..", "renders",
                           "perturbation_roundtrip.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nReport: {out}")

    else:
        parser.print_help()