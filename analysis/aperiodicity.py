#!/usr/bin/env python3
"""
VOICE — Phase 2 Step 2: Band aperiodicity in the vowel path
============================================================
Mix band-shaped noise into the existing vowel synth at the genome's
per-band targets. Per-band noise levels are set relative to harmonic
energy in each band.

Raven grain: 1000-3000 Hz, -24 dB (≈6% of harmonic level) — rasp
Sibilance: 5000-9000 Hz, 2-3 dB shelf — ghost of a hiss
Breathiness: broadband aspiration (low-level)

Usage:
  python aperiodicity.py --demo        # synthesize /ɑ/ with aperiodicity
"""

import argparse
import json
import os
import sys

import numpy as np
from scipy.io import wavfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from noise_source import BANDS

SR = 48000

APERIODICITY_TARGETS = {
    "raven_grain": {"band": (1000, 3000), "level_db": -24.0},
    "sibilance": {"band": (5000, 9000), "shelf_db": 2.5},
    "breathiness": {"band": (0, 16000), "level_db": -30.0},
}


def add_aperiodicity(harmonic_signal, sr=SR, targets=None, seed=42):
    """Mix band-shaped aperiodicity noise into a harmonic vowel signal.

    Per-band noise levels are set relative to harmonic energy in each
    band, matching the genome's aperiodicity targets.

    Returns: (mixed_signal, noise_component)
    """
    if targets is None:
        targets = APERIODICITY_TARGETS

    n_samples = len(harmonic_signal)

    # Normalize harmonic
    harm_peak = np.max(np.abs(harmonic_signal))
    if harm_peak > 0:
        harmonic_norm = harmonic_signal / harm_peak * 0.5
    else:
        harmonic_norm = harmonic_signal.copy()

    # Generate white noise
    rng = np.random.default_rng(seed)
    white_noise = rng.normal(0, 1, n_samples)

    # FFT both
    fft_h = np.fft.rfft(harmonic_norm)
    fft_n = np.fft.rfft(white_noise)
    freqs = np.fft.rfftfreq(n_samples, 1.0 / sr)

    # Per-band: scale noise to target ratio relative to harmonic
    scaled_fft_n = np.zeros_like(fft_n, dtype=complex)
    for name, lo, hi, _ in BANDS:
        mask = (freqs >= lo) & (freqs < hi)
        if not np.any(mask):
            continue

        # Target dB for this band
        if name == "raven_grain":
            target_db = targets["raven_grain"]["level_db"]
        elif name == "sibilance":
            target_db = targets["sibilance"]["shelf_db"]
        else:
            target_db = targets["breathiness"]["level_db"]

        # Harmonic energy in this band
        harm_band_energy = np.mean(np.abs(fft_h[mask]) ** 2)
        if harm_band_energy < 1e-20:
            harm_band_energy = 1e-20

        # Desired noise energy in this band
        target_ratio = 10 ** (target_db / 10.0)
        desired_noise_energy = harm_band_energy * target_ratio

        # Current noise energy in this band
        noise_band_energy = np.mean(np.abs(fft_n[mask]) ** 2)
        if noise_band_energy < 1e-20:
            noise_band_energy = 1e-20

        # Scale factor for this band
        scale = np.sqrt(desired_noise_energy / noise_band_energy)

        # Apply scale
        scaled_fft_n[mask] = fft_n[mask] * scale

    # Inverse FFT
    noise = np.fft.irfft(scaled_fft_n, n=n_samples)

    # Mix
    mixed = harmonic_norm + noise

    # Normalize to prevent clipping
    peak = np.max(np.abs(mixed))
    if peak > 0:
        mixed = mixed / peak * 0.5
        noise = noise / peak * 0.5
        harmonic_norm = harmonic_norm / peak * 0.5

    return mixed, noise


def measure_aperiodicity(harmonic_signal, mixed_signal, sr=SR):
    """Measure per-band noise-to-harmonic ratios.

    Returns dict with per-band ratios in dB.
    """
    from scipy.signal import welch

    noise_signal = mixed_signal - harmonic_signal

    _, psd_h = welch(harmonic_signal, fs=sr, nperseg=min(2048, len(harmonic_signal) // 4),
                    noverlap=None, window='hann')
    _, psd_n = welch(noise_signal, fs=sr, nperseg=min(2048, len(noise_signal) // 4),
                    noverlap=None, window='hann')

    freqs = np.fft.rfftfreq(len(psd_h) * 2 - 1, 1.0 / sr)[:len(psd_h)]

    result = {}
    for name, lo, hi, _ in BANDS:
        mask = (freqs >= lo) & (freqs < hi)
        if np.any(mask):
            harm_energy = np.mean(psd_h[mask])
            noise_energy = np.mean(psd_n[mask])
            if harm_energy > 0 and noise_energy > 0:
                ratio_db = 10 * np.log10(noise_energy / harm_energy)
            else:
                ratio_db = -99
            result[name] = {
                "noise_to_harmonic_db": round(float(ratio_db), 1),
            }
        else:
            result[name] = {"noise_to_harmonic_db": -99}

    return result


def demo(sr=SR, duration=2.0, seed=42):
    """Demo: synthesize /ɑ/ with and without aperiodicity, save both."""
    import yaml
    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    with open(genome_path) as f:
        genome = yaml.safe_load(f)

    f0 = 190.0
    rng = np.random.default_rng(seed)
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from phase1_synth import render_vowel
    harmonic = render_vowel(genome, "ɑ", f0, duration, "simple", rng)
    mixed, noise = add_aperiodicity(harmonic, sr=sr, seed=seed)
    measurements = measure_aperiodicity(harmonic, mixed, sr=sr)

    out_dir = os.path.join(os.path.dirname(__file__), "..", "renders")
    os.makedirs(out_dir, exist_ok=True)
    wavfile.write(os.path.join(out_dir, "vowel_ɑ_harmonic.wav"), sr,
                  (harmonic * 32767).astype(np.int16))
    wavfile.write(os.path.join(out_dir, "vowel_ɑ_with_aperiodicity.wav"), sr,
                  (mixed * 32767).astype(np.int16))
    wavfile.write(os.path.join(out_dir, "vowel_ɑ_noise_component.wav"), sr,
                  (noise * 32767).astype(np.int16))

    print("Aperiodicity measurements for /ɑ/:")
    for band, info in measurements.items():
        print(f"  {band}: noise/harmonic = {info['noise_to_harmonic_db']} dB")

    return harmonic, mixed, noise, measurements


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VOICE aperiodicity")
    parser.add_argument("--demo", action="store_true",
                        help="Synthesize /ɑ/ with and without aperiodicity")
    parser.add_argument("--sr", type=int, default=SR)
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.demo:
        harmonic, mixed, noise, measurements = demo(sr=args.sr, duration=args.duration,
                                                   seed=args.seed)
        out = os.path.join(os.path.dirname(__file__), "..", "renders",
                           "aperiodicity_measurements.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(measurements, f, indent=2)
        print(f"\nMeasurements saved: {out}")

    else:
        parser.print_help()