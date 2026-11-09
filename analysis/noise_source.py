#!/usr/bin/env python3
"""
VOICE — Noise source for Phase 2 (band-shaped aperiodicity)
============================================================
One noise generator with per-band gain matching the genome's
aperiodicity bands. Characterized before anything consumes it:
flat input, measured band energies match commanded energies.

Phase 0 discipline: the source gets a round-trip before the
consumers get built on it.

Bands (from genome + voice spectrum coverage):
  1. 0-500 Hz: sub-bass rumble (breathiness foundation)
  2. 500-1000 Hz: low warmth
  3. 1000-3000 Hz: raven grain (genome: raven_grain band_hz)
  4. 3000-5000 Hz: mid transition
  5. 5000-9000 Hz: sibilance (genome: sibilance band_hz)
  6. 9000-16000 Hz: air/brightness

Usage:
  python noise_source.py --characterize   # round-trip test
  python noise_source.py --demo           # generate sample noise
"""

import argparse
import json
import os
import sys

import numpy as np
from scipy.signal import welch

SR = 48000

# Bands: (name, low_hz, high_hz, genome_reference)
BANDS = [
    ("sub_bass", 0, 500, "sub_bass (indirect)"),
    ("low_warmth", 500, 1000, None),
    ("raven_grain", 1000, 3000, "raven_grain band_hz [1000, 3000]"),
    ("mid_transition", 3000, 5000, None),
    ("sibilance", 5000, 9000, "sibilance band_hz [5000, 9000]"),
    ("air", 9000, 16000, None),
]


class NoiseSource:
    """Band-shaped noise generator with per-band gain control.

    Generates white noise, applies per-band gains via FFT masking,
    returns shaped noise. Each band's gain is independently controllable.
    """

    def __init__(self, sr=SR, duration=1.0, seed=None):
        self.sr = sr
        self.duration = duration
        self.n_samples = int(duration * sr)
        self.rng = np.random.default_rng(seed)
        # Per-band gains in dB (default: flat, 0 dB all bands)
        self.band_gains_db = {name: 0.0 for name, _, _, _ in BANDS}

    def set_band_gain(self, band_name, gain_db):
        """Set gain for a specific band in dB."""
        if band_name not in self.band_gains_db:
            raise ValueError(f"Unknown band: {band_name}. "
                            f"Available: {list(self.band_gains_db.keys())}")
        self.band_gains_db[band_name] = gain_db

    def set_band_gains(self, gains_dict):
        """Set gains for multiple bands at once."""
        for name, gain in gains_dict.items():
            self.set_band_gain(name, gain)

    def generate(self):
        """Generate shaped noise with current band gains."""
        # Generate white noise
        noise = self.rng.normal(0, 1, self.n_samples)

        # FFT
        fft = np.fft.rfft(noise)
        freqs = np.fft.rfftfreq(self.n_samples, 1.0 / self.sr)

        # Apply per-band gains
        for name, lo, hi, _ in BANDS:
            gain_db = self.band_gains_db[name]
            gain_linear = 10 ** (gain_db / 20.0)
            mask = (freqs >= lo) & (freqs < hi)
            fft[mask] *= gain_linear

        # Inverse FFT
        shaped = np.fft.irfft(fft, n=self.n_samples)

        # Normalize to prevent clipping
        peak = np.max(np.abs(shaped))
        if peak > 0:
            shaped = shaped / peak * 0.5

        return shaped

    def measure_band_energies(self, signal=None):
        """Measure energy in each band. If signal is None, generate first."""
        if signal is None:
            signal = self.generate()

        freqs, psd = welch(signal, fs=self.sr, nperseg=min(2048, len(signal) // 4),
                           noverlap=None, window='hann')

        result = {}
        for name, lo, hi, _ in BANDS:
            mask = (freqs >= lo) & (freqs < hi)
            if np.any(mask):
                band_energy = np.mean(psd[mask])
                band_db = 10 * np.log10(band_energy) if band_energy > 0 else -99
            else:
                band_energy = 0.0
                band_db = -99
            result[name] = {
                "energy": float(band_energy),
                "db": round(float(band_db), 1),
                "gain_db": self.band_gains_db[name],
            }
        return result


def characterize(sr=SR, duration=1.0, seed=42):
    """Round-trip characterization: command band energies, measure them back.

    Tests:
    1. Flat (all bands 0 dB): measured energies should be roughly equal
    2. Single band boosted: only that band should show elevated energy
    3. Single band cut: only that band should show reduced energy
    4. All bands at different gains: measured ratios should match commanded
    """
    results = {"tests": [], "passed": True, "notes": []}

    # Test 1: Flat (all 0 dB)
    src = NoiseSource(sr=sr, duration=duration, seed=seed)
    flat_energies = src.measure_band_energies()
    # Check: all bands within 3 dB of each other (white noise is flat)
    dbs = [v["db"] for v in flat_energies.values() if v["db"] > -90]
    spread = max(dbs) - min(dbs) if dbs else 99
    test1_pass = spread < 6.0  # 6 dB tolerance for Welch estimation
    results["tests"].append({
        "name": "flat_all_bands",
        "description": "All bands at 0 dB — measured energies should be roughly equal",
        "passed": test1_pass,
        "spread_db": round(spread, 1),
        "tolerance_db": 6.0,
        "details": flat_energies,
    })
    if not test1_pass:
        results["passed"] = False
        results["notes"].append(f"Flat test: spread {spread:.1f} dB > 6 dB tolerance")

    # Test 2: Single band boosted (+12 dB)
    for boost_band in ["raven_grain", "sibilance"]:
        src = NoiseSource(sr=sr, duration=duration, seed=seed)
        src.set_band_gain(boost_band, 12.0)
        boosted = src.measure_band_energies()
        # The boosted band should be ~12 dB higher than the others
        boosted_db = boosted[boost_band]["db"]
        other_dbs = [v["db"] for k, v in boosted.items() if k != boost_band and v["db"] > -90]
        mean_other = np.mean(other_dbs) if other_dbs else -99
        diff = boosted_db - mean_other
        test_pass = 9.0 < diff < 15.0  # 12 dB ± 3 dB
        results["tests"].append({
            "name": f"boost_{boost_band}",
            "description": f"Boost {boost_band} by +12 dB — should be ~12 dB above others",
            "passed": test_pass,
            "boosted_band_db": boosted_db,
            "mean_other_db": round(float(mean_other), 1),
            "measured_diff_db": round(float(diff), 1),
            "target_diff_db": 12.0,
            "tolerance_db": 3.0,
            "details": boosted,
        })
        if not test_pass:
            results["passed"] = False
            results["notes"].append(
                f"Boost {boost_band}: diff {diff:.1f} dB (expected 12 ± 3)")

    # Test 3: Single band cut (-12 dB)
    for cut_band in ["raven_grain", "sibilance"]:
        src = NoiseSource(sr=sr, duration=duration, seed=seed)
        src.set_band_gain(cut_band, -12.0)
        cut = src.measure_band_energies()
        cut_db = cut[cut_band]["db"]
        other_dbs = [v["db"] for k, v in cut.items() if k != cut_band and v["db"] > -90]
        mean_other = np.mean(other_dbs) if other_dbs else -99
        diff = mean_other - cut_db
        test_pass = 9.0 < diff < 15.0
        results["tests"].append({
            "name": f"cut_{cut_band}",
            "description": f"Cut {cut_band} by -12 dB — should be ~12 dB below others",
            "passed": test_pass,
            "cut_band_db": cut_db,
            "mean_other_db": round(float(mean_other), 1),
            "measured_diff_db": round(float(diff), 1),
            "target_diff_db": 12.0,
            "tolerance_db": 3.0,
            "details": cut,
        })
        if not test_pass:
            results["passed"] = False
            results["notes"].append(
                f"Cut {cut_band}: diff {diff:.1f} dB (expected 12 ± 3)")

    # Test 4: Multi-band (different gains per band)
    src = NoiseSource(sr=sr, duration=duration, seed=seed)
    gains = {"raven_grain": 6.0, "sibilance": -6.0, "air": 3.0}
    src.set_band_gains(gains)
    multi = src.measure_band_energies()
    # Check ratios
    multi_pass = True
    for band, gain in gains.items():
        measured_db = multi[band]["db"]
        # Find a reference band (one at 0 dB)
        ref_db = multi["low_warmth"]["db"]
        diff = measured_db - ref_db
        if abs(diff - gain) > 4.0:
            multi_pass = False
            results["notes"].append(
                f"Multi-band: {band} diff {diff:.1f} dB (expected {gain} ± 4)")
    results["tests"].append({
        "name": "multi_band",
        "description": "Multiple bands at different gains — ratios should match",
        "passed": multi_pass,
        "commanded_gains": gains,
        "details": multi,
    })
    if not multi_pass:
        results["passed"] = False

    return results


def demo(sr=SR, duration=2.0, seed=42):
    """Generate a sample noise with raven grain + sibilance at genome levels."""
    src = NoiseSource(sr=sr, duration=duration, seed=seed)
    # Raven grain at -24 dB (≈6% of harmonic level) → noise gain
    # In practice, aperiodicity is mixed with harmonics, so the noise
    # level is relative to the harmonic signal. For standalone noise,
    # we set raven grain slightly above flat and sibilance lower.
    src.set_band_gain("raven_grain", -12.0)  # subtle
    src.set_band_gain("sibilance", -18.0)    # more subtle
    src.set_band_gain("air", -24.0)          # very subtle
    return src.generate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VOICE noise source")
    parser.add_argument("--characterize", action="store_true",
                        help="Run round-trip characterization")
    parser.add_argument("--demo", action="store_true",
                        help="Generate demo noise and print band energies")
    parser.add_argument("--sr", type=int, default=SR)
    parser.add_argument("--duration", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.characterize:
        results = characterize(sr=args.sr, duration=args.duration, seed=args.seed)
        print(f"\nNoise source characterization: "
              f"{'ALL PASS' if results['passed'] else 'FAILURES'}")
        for t in results["tests"]:
            print(f"  {t['name']}: {'PASS' if t['passed'] else 'FAIL'}")
        if results["notes"]:
            print("Notes:")
            for n in results["notes"]:
                print(f"  - {n}")
        out = os.path.join(os.path.dirname(__file__), "..", "renders",
                           "noise_char.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        # Convert numpy types to Python types for JSON
        def _convert(obj):
            if isinstance(obj, (np.bool_,)):
                return bool(obj)
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_convert(v) for v in obj]
            return obj
        with open(out, "w") as f:
            json.dump(_convert(results), f, indent=2)
        print(f"\nReport: {out}")

    elif args.demo:
        noise = demo(sr=args.sr, duration=args.duration, seed=args.seed)
        src = NoiseSource(sr=args.sr, duration=args.duration, seed=args.seed)
        src.set_band_gain("raven_grain", -12.0)
        src.set_band_gain("sibilance", -18.0)
        src.set_band_gain("air", -24.0)
        energies = src.measure_band_energies(noise)
        print("Demo noise band energies:")
        for name, info in energies.items():
            print(f"  {name}: {info['db']} dB (gain: {info['gain_db']} dB)")
        out = os.path.join(os.path.dirname(__file__), "..", "renders",
                           "noise_demo.wav")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        from scipy.io import wavfile
        wavfile.write(out, args.sr, (noise * 32767).astype(np.int16))
        print(f"Saved: {out}")

    else:
        parser.print_help()