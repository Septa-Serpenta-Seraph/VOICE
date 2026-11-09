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

Supports both simple (pulse-train) and LF (Fant 1985) sources.

Usage:
  python perturbation.py --demo     # synthesize with perturbation
  python perturbation.py --test     # round-trip test
  python perturbation.py --test --source lf  # LF source round-trip
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


def _slow_drift_envelope(duration, sr, rng, n_drift_samples_per_sec=100):
    """Generate slow drift envelope (0.3-0.7 Hz band-limited noise)."""
    n_drift_samples = int(duration * n_drift_samples_per_sec)
    drift_noise = rng.normal(0, 1, n_drift_samples)
    from scipy.signal import butter, filtfilt
    nyq = n_drift_samples_per_sec / 2
    low = 0.3 / nyq
    high = 0.7 / nyq
    b_filt, a_filt = butter(2, [low, high], btype='band')
    drift_filtered = filtfilt(b_filt, a_filt, drift_noise)
    drift_std = np.std(drift_filtered)
    if drift_std > 0:
        drift_filtered = drift_filtered / drift_std
    drift_t = np.linspace(0, duration, n_drift_samples)
    drift_t_full = np.arange(int(duration * sr)) / sr
    drift_envelope = np.interp(drift_t_full, drift_t, drift_filtered)
    return drift_envelope


def perturbed_pulse_train(f0, duration, sr, jitter_pct=JITTER_TARGET,
                          shimmer_pct=SHIMMER_TARGET, seed=42, trim_onset=0.25):
    """Generate a perturbed glottal pulse train with structured jitter+shimmer.

    Structure: slow_drift_plus_cycle (Round 2 specification, Round 9 rebuild).
    """
    rng = np.random.default_rng(seed)
    n_samples = int(duration * sr)
    onset_trim = int(trim_onset * sr)

    drift_envelope = _slow_drift_envelope(duration, sr, rng)
    drift_depth = 0.2
    drift_contribution = drift_envelope * (jitter_pct / 100.0 * drift_depth)

    cycle_sigma_jitter = (jitter_pct / 100.0) / 1.13
    cycle_sigma_shimmer = (shimmer_pct / 100.0) / 1.13

    signal = np.zeros(n_samples)
    pos = 0
    periods = []
    amplitudes = []

    while pos < n_samples:
        drift_mod = drift_contribution[pos] if pos < len(drift_contribution) else 0.0
        cycle_jitter = rng.normal(0, cycle_sigma_jitter) + drift_mod
        period_samples = int(round(sr / f0 * (1.0 + cycle_jitter)))
        period_samples = max(period_samples, 8)

        cycle_shimmer = rng.normal(0, cycle_sigma_shimmer)
        amplitude = 1.0 + cycle_shimmer

        if pos < n_samples:
            signal[pos] = amplitude

        periods.append(period_samples)
        amplitudes.append(amplitude)
        pos += period_samples

    signal = lfilter([1.0], [1.0, -0.95], signal)

    wander = 1.0 + 0.01 * np.sin(2 * np.pi * 0.3 * np.arange(n_samples) / sr)
    signal = signal * wander

    periods = np.array(periods)
    amplitudes = np.array(amplitudes)
    if len(periods) > 1:
        period_diffs = np.abs(np.diff(periods))
        injected_jitter = np.mean(period_diffs) / np.mean(periods) * 100
    else:
        injected_jitter = 0.0
    if len(amplitudes) > 1:
        amp_diffs = np.abs(np.diff(amplitudes))
        injected_shimmer = np.mean(amp_diffs) / np.mean(np.abs(amplitudes)) * 100
    else:
        injected_shimmer = 0.0

    if len(periods) > 10:
        period_devs = periods - np.mean(periods)
        fft = np.abs(np.fft.rfft(period_devs))
        freqs = np.fft.rfftfreq(len(period_devs), d=1.0)
        slow_power = np.sum(fft[freqs < 1.0]**2)
        total_power = np.sum(fft**2)
        slow_drift_pct = (slow_power / total_power * 100) if total_power > 0 else 0.0
    else:
        slow_drift_pct = 0.0

    injected_stats = {
        "injected_jitter_pct": round(float(injected_jitter), 3),
        "injected_shimmer_pct": round(float(injected_shimmer), 3),
        "n_cycles": len(periods),
        "slow_drift_power_pct": round(float(slow_drift_pct), 1),
        "jitter_target": jitter_pct,
        "shimmer_target": shimmer_pct,
    }

    return signal, onset_trim, injected_stats


def perturbed_lf_source(f0, duration, sr, rd=1.0, jitter_pct=JITTER_TARGET,
                        shimmer_pct=SHIMMER_TARGET, seed=42, trim_onset=0.25):
    """Generate a perturbed LF glottal source with slow-drift-plus-cycle structure.

    Uses the Fant 1985 / Doval 2006 LF model with the same perturbation
    structure as perturbed_pulse_train.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from analysis.phase1_synth import lf_timing_from_rd, _lf_alpha

    rng = np.random.default_rng(seed)
    n_samples = int(duration * sr)
    onset_trim = int(trim_onset * sr)

    tp, te, ta = lf_timing_from_rd(rd, f0)
    t0 = 1.0 / f0

    drift_envelope = _slow_drift_envelope(duration, sr, rng)
    drift_depth = 0.2
    drift_contribution = drift_envelope * (jitter_pct / 100.0 * drift_depth)

    cycle_sigma_jitter = (jitter_pct / 100.0) / 1.13
    cycle_sigma_shimmer = (shimmer_pct / 100.0) / 1.13

    signal = np.zeros(n_samples)
    pos = 0
    periods = []
    amplitudes = []

    while pos < n_samples:
        drift_mod = drift_contribution[pos] if pos < len(drift_contribution) else 0.0
        cycle_jitter = rng.normal(0, cycle_sigma_jitter) + drift_mod
        period_samples = int(round(sr / f0 * (1.0 + cycle_jitter)))
        period_samples = max(period_samples, 8)

        cycle_shimmer = rng.normal(0, cycle_sigma_shimmer)
        amplitude = 1.0 + cycle_shimmer

        n = min(period_samples, n_samples - pos)
        t = np.arange(n) / sr
        te_c = te * (1.0 + cycle_jitter)
        alpha, omega, eps = _lf_alpha(tp, te, ta, t0)

        val_te_open = amplitude * np.exp(alpha * te_c) * np.sin(omega * te_c)
        denom = 1.0 - np.exp(-eps * (t0 - te_c))
        A = -val_te_open / denom if abs(denom) > 1e-10 else 0.0

        cyc = np.where(
            t < te_c,
            amplitude * np.exp(alpha * t) * np.sin(omega * t),
            -A * (np.exp(-eps * (t - te_c)) - np.exp(-eps * (t0 - te_c))),
        )
        signal[pos:pos + n] += cyc
        periods.append(period_samples)
        amplitudes.append(amplitude)
        pos += period_samples

    wander = 1.0 + 0.01 * np.sin(2 * np.pi * 0.3 * np.arange(n_samples) / sr)
    signal = signal * wander

    periods = np.array(periods)
    amplitudes = np.array(amplitudes)
    if len(periods) > 1:
        period_diffs = np.abs(np.diff(periods))
        injected_jitter = np.mean(period_diffs) / np.mean(periods) * 100
    else:
        injected_jitter = 0.0
    if len(amplitudes) > 1:
        amp_diffs = np.abs(np.diff(amplitudes))
        injected_shimmer = np.mean(amp_diffs) / np.mean(np.abs(amplitudes)) * 100
    else:
        injected_shimmer = 0.0

    if len(periods) > 10:
        period_devs = periods - np.mean(periods)
        fft = np.abs(np.fft.rfft(period_devs))
        freqs = np.fft.rfftfreq(len(period_devs), d=1.0)
        slow_power = np.sum(fft[freqs < 1.0]**2)
        total_power = np.sum(fft**2)
        slow_drift_pct = (slow_power / total_power * 100) if total_power > 0 else 0.0
    else:
        slow_drift_pct = 0.0

    injected_stats = {
        "injected_jitter_pct": round(float(injected_jitter), 3),
        "injected_shimmer_pct": round(float(injected_shimmer), 3),
        "n_cycles": len(periods),
        "slow_drift_power_pct": round(float(slow_drift_pct), 1),
        "jitter_target": jitter_pct,
        "shimmer_target": shimmer_pct,
    }

    return signal, onset_trim, injected_stats


def synthesize_perturbed_vowel(vowel, genome, f0, duration, sr=SR, seed=42,
                                jitter_pct=JITTER_TARGET, shimmer_pct=SHIMMER_TARGET,
                                source_kind="simple"):
    """Synthesize a vowel with perturbation, ready for Praat measurement."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from phase1_synth import render_vowel

    # Generate perturbed source
    if source_kind == "lf":
        rd = genome["source"]["rd"]["default"]
        source, onset_trim, injected = perturbed_lf_source(
            f0, duration, sr, rd=rd, jitter_pct=jitter_pct,
            shimmer_pct=shimmer_pct, seed=seed
        )
    else:
        source, onset_trim, injected = perturbed_pulse_train(
            f0, duration, sr, jitter_pct=jitter_pct,
            shimmer_pct=shimmer_pct, seed=seed
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

    # Apply formant filters (parallel resonator bank) with genome bandwidths
    bw_map = {"F1": 80, "F2": 100, "F3": 120, "F4": 150}
    n_samples = len(source)
    output = np.zeros(n_samples)
    for name, f_freq in formants.items():
        bw = bw_map[name]
        w0 = 2 * np.pi * f_freq / sr
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

    return output, onset_trim, injected


def measure_jitter_shimmer_praat(signal, sr, f0=190.0):
    """Measure jitter and shimmer using Praat via parselmouth."""
    import parselmouth
    from parselmouth.praat import call

    snd = parselmouth.Sound(signal, sampling_frequency=sr)
    pp = call(snd, "To PointProcess (periodic, cc)", f0 * 0.8, f0 * 1.2)

    jitter = call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
    shimmer = call([pp, snd], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
    n_cycles = call(pp, "Get number of points")

    return {
        "jitter_local_pct": round(jitter * 100, 3) if jitter is not None else None,
        "shimmer_local_pct": round(shimmer * 100, 3) if shimmer is not None else None,
        "n_cycles": int(n_cycles) if n_cycles is not None else 0,
    }


def round_trip_test(genome, f0=190.0, duration=3.0, sr=SR, seed=42,
                    source_kind="simple"):
    """Round-trip test with configurable source."""
    known_jitter = JITTER_TARGET
    known_shimmer = SHIMMER_TARGET

    signal, onset_trim, injected = synthesize_perturbed_vowel(
        "ɑ", genome, f0, duration, sr=sr, seed=seed,
        jitter_pct=known_jitter, shimmer_pct=known_shimmer,
        source_kind=source_kind
    )

    trimmed = signal[onset_trim:]
    result = measure_jitter_shimmer_praat(trimmed, sr, f0=f0)

    got_j = result["jitter_local_pct"]
    got_s = result["shimmer_local_pct"]

    recovered_j = (got_j is not None and
                   abs(got_j - injected["injected_jitter_pct"]) < 0.3)
    recovered_s = (got_s is not None and
                   abs(got_s - injected["injected_shimmer_pct"]) < 1.0)

    return {
        "source_kind": source_kind,
        "known_jitter_pct": known_jitter,
        "injected_jitter_pct": injected["injected_jitter_pct"],
        "measured_jitter_pct": got_j,
        "jitter_recovered": recovered_j,
        "known_shimmer_pct": known_shimmer,
        "injected_shimmer_pct": injected["injected_shimmer_pct"],
        "measured_shimmer_pct": got_s,
        "shimmer_recovered": recovered_s,
        "n_cycles": result["n_cycles"],
        "slow_drift_power_pct": injected["slow_drift_power_pct"],
        "round_trip_passed": recovered_j and recovered_s,
    }


def demo(sr=SR, duration=3.0, seed=42, source_kind="simple"):
    """Demo: synthesize /ɑ/ with perturbation and save."""
    import yaml
    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    with open(genome_path) as f:
        genome = yaml.safe_load(f)

    f0 = 190.0
    signal, onset_trim, injected = synthesize_perturbed_vowel(
        "ɑ", genome, f0, duration, sr=sr, seed=seed, source_kind=source_kind
    )

    out_dir = os.path.join(os.path.dirname(__file__), "..", "renders")
    os.makedirs(out_dir, exist_ok=True)
    suffix = f"_{source_kind}" if source_kind != "simple" else ""
    wavfile.write(os.path.join(out_dir, f"vowel_ɑ_perturbed{suffix}.wav"), sr,
                  (signal * 32767).astype(np.int16))
    wavfile.write(os.path.join(out_dir, f"vowel_ɑ_perturbed{suffix}_trimmed.wav"), sr,
                  (signal[onset_trim:] * 32767).astype(np.int16))

    result = measure_jitter_shimmer_praat(signal[onset_trim:], sr, f0=f0)
    print(f"Perturbed /ɑ/ (trimmed, source={source_kind}):")
    print(f"  Jitter: {result['jitter_local_pct']}% (target: {JITTER_TARGET}%)")
    print(f"  Shimmer: {result['shimmer_local_pct']}% (target: {SHIMMER_TARGET}%)")
    print(f"  Cycles: {result['n_cycles']}")
    print(f"  Injected jitter: {injected['injected_jitter_pct']}% (slow drift: {injected['slow_drift_power_pct']}%)")
    print(f"  Injected shimmer: {injected['injected_shimmer_pct']}%")

    return signal, result, injected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VOICE perturbation")
    parser.add_argument("--demo", action="store_true",
                        help="Synthesize /ɑ/ with perturbation")
    parser.add_argument("--test", action="store_true",
                        help="Run round-trip test")
    parser.add_argument("--source", choices=["simple", "lf"], default="simple",
                        help="Source: simple pulse-train or LF glottal model")
    parser.add_argument("--sr", type=int, default=SR)
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    import yaml
    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    with open(genome_path) as f:
        genome = yaml.safe_load(f)

    if args.demo:
        signal, result, injected = demo(sr=args.sr, duration=args.duration,
                                       seed=args.seed, source_kind=args.source)

    elif args.test:
        result = round_trip_test(genome, f0=190.0, duration=args.duration,
                                sr=args.sr, seed=args.seed,
                                source_kind=args.source)
        print(f"\nRound-trip test (source={args.source}):")
        print(f"  Jitter: {result['known_jitter_pct']}% in → "
              f"{result['measured_jitter_pct']}% out "
              f"({'PASS' if result['jitter_recovered'] else 'FAIL'})")
        print(f"  Shimmer: {result['known_shimmer_pct']}% in → "
              f"{result['measured_shimmer_pct']}% out "
              f"({'PASS' if result['shimmer_recovered'] else 'FAIL'})")
        print(f"  Cycles: {result['n_cycles']}")
        print(f"  Overall: {'PASS' if result['round_trip_passed'] else 'FAIL'}")

        out = os.path.join(os.path.dirname(__file__), "..", "renders",
                           f"perturbation_roundtrip_{args.source}.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nReport: {out}")

    else:
        parser.print_help()