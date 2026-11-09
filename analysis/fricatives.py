#!/usr/bin/env python3
"""
VOICE — Phase 2 Step 3: Fricative branch
========================================
Parallel branch: noise through per-fricative filter sets, mixed against
the vowel path. Voicing mix for /z v ð ʒ/ (periodic + noise simultaneously).

Fricative targets (literature starting points, after Forrest 1988;
Jongman, Wayland & Wong 2000). To be ear-tuned.

Spectral moments: centroid, spread, skew over steady frication window.
First-pass windows: ±15% on centroid.

Usage:
  python fricatives.py --demo        # synthesize all fricatives
  python fricatives.py --measure     # measure spectral moments
"""

import argparse
import json
import os
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter, welch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from noise_source import NoiseSource

SR = 48000

# Fricative filter specifications (center frequency, bandwidth, type)
# Based on literature spectral moments for female speakers
FRICATIVE_SPECS = {
    "/s/":  {"center": 7000, "bw": 2000, "type": "bandpass", "voiced": False},
    "/z/":  {"center": 6500, "bw": 2000, "type": "bandpass", "voiced": True},
    "/ʃ/":  {"center": 4000, "bw": 2500, "type": "bandpass", "voiced": False},
    "/ʒ/":  {"center": 3700, "bw": 2500, "type": "bandpass", "voiced": True},
    "/f/":  {"center": 3000, "bw": 4000, "type": "bandpass", "voiced": False},
    "/v/":  {"center": 3000, "bw": 4000, "type": "bandpass", "voiced": True},
    "/θ/":  {"center": 5000, "bw": 6000, "type": "bandpass", "voiced": False},
    "/ð/":  {"center": 5000, "bw": 6000, "type": "bandpass", "voiced": True},
    "/h/":  {"center": 0,    "bw": 0,     "type": "aspiration", "voiced": False},
}

# Target centroids from literature (Hz)
FRICATIVE_TARGETS = {
    "/s/":  {"centroid": 7000, "tolerance_pct": 15},
    "/z/":  {"centroid": 6500, "tolerance_pct": 15},
    "/ʃ/":  {"centroid": 4000, "tolerance_pct": 15},
    "/ʒ/":  {"centroid": 3700, "tolerance_pct": 15},
    "/f/":  {"centroid": None, "tolerance_pct": None},  # diffuse
    "/v/":  {"centroid": None, "tolerance_pct": None},
    "/θ/":  {"centroid": None, "tolerance_pct": None},
    "/ð/":  {"centroid": None, "tolerance_pct": None},
    "/h/":  {"centroid": None, "tolerance_pct": None},  # formant-shaped
}


def make_fricative_filter(spec, sr=SR):
    """Create a filter for a fricative based on its spec.

    Returns a function that filters a signal.
    """
    ftype = spec["type"]

    if ftype == "highpass":
        # Highpass: emphasize high frequencies
        # Simple: subtract lowpass
        from scipy.signal import butter, sosfilt
        sos = butter(2, spec["center"] / (sr / 2), btype='highpass', output='sos')
        return lambda x: sosfilt(sos, x)

    elif ftype == "bandpass":
        from scipy.signal import butter, sosfilt
        low = max(100, spec["center"] - spec["bw"] // 2)
        high = min(sr // 2 - 100, spec["center"] + spec["bw"] // 2)
        sos = butter(2, [low / (sr / 2), high / (sr / 2)], btype='bandpass', output='sos')
        return lambda x: sosfilt(sos, x)

    elif ftype == "diffuse":
        # Weak, flat spectrum — just attenuate
        return lambda x: x * 0.3

    elif ftype == "diffuse_weak":
        return lambda x: x * 0.15

    elif ftype == "aspiration":
        # Formant-shaped: will be handled separately with vowel grid
        return lambda x: x * 0.5

    return lambda x: x


def synthesize_fricative(fricative, duration=0.5, sr=SR, seed=42, f0=190.0,
                         vowel_formants=None):
    """Synthesize a fricative.

    Parameters:
        fricative: fricative symbol (e.g., "/s/")
        duration: duration in seconds
        sr: sample rate
        seed: random seed
        f0: fundamental frequency (for voiced fricatives)
        vowel_formants: formants for /h/ aspiration (optional)

    Returns:
        signal array
    """
    spec = FRICATIVE_SPECS[fricative]
    n_samples = int(duration * sr)
    rng = np.random.default_rng(seed)

    # Generate noise
    src = NoiseSource(sr=sr, duration=duration, seed=seed)
    noise = src.generate()

    # Apply fricative filter
    filt = make_fricative_filter(spec, sr)
    filtered_noise = filt(noise)

    # For voiced fricatives, mix with glottal source
    if spec["voiced"]:
        # Generate glottal pulse train
        period = int(sr / f0)
        glottal = np.zeros(n_samples)
        for i in range(0, n_samples, period):
            glottal[i] = 1.0
        from scipy.signal import lfilter
        # For voiced fricatives: weak glottal buzz, highpass to remove low freqs
        glottal = lfilter([1.0], [1.0, -0.95], glottal)
        # Highpass the glottal to remove F0 dominance
        from scipy.signal import butter, sosfilt
        sos = butter(2, 1000 / (sr / 2), btype='highpass', output='sos')
        glottal = sosfilt(sos, glottal)
        # Mix: 90% noise, 10% glottal (voicing is subtle in fricatives)
        signal = 0.9 * filtered_noise + 0.1 * glottal
    else:
        signal = filtered_noise

    # For /h/, shape by vowel formants
    if fricative == "/h/" and vowel_formants:
        from phase1_synth import synthesize_vowel
        # Use aspiration shaped by formants
        aspiration = synthesize_vowel(f0, vowel_formants, duration, sr)
        signal = signal * 0.3 + aspiration * 0.7

    # Normalize
    peak = np.max(np.abs(signal))
    if peak > 0:
        signal = signal / peak * 0.5

    return signal


def measure_spectral_moments(signal, sr=SR):
    """Measure spectral moments (centroid, spread, skew) over the signal.

    Returns dict with centroid_hz, spread_hz, skew.
    """
    freqs, psd = welch(signal, fs=sr, nperseg=min(2048, len(signal) // 4),
                       noverlap=None, window='hann')

    # Normalize PSD
    total_power = np.sum(psd)
    if total_power == 0:
        return {"centroid_hz": 0, "spread_hz": 0, "skew": 0}

    # Centroid
    centroid = np.sum(freqs * psd) / total_power

    # Spread (standard deviation)
    spread = np.sqrt(np.sum((freqs - centroid) ** 2 * psd) / total_power)

    # Skew
    skew = np.sum((freqs - centroid) ** 3 * psd) / (total_power * spread ** 3) if spread > 0 else 0

    return {
        "centroid_hz": round(float(centroid), 1),
        "spread_hz": round(float(spread), 1),
        "skew": round(float(skew), 3),
    }


def check_fricative(fricative, moments):
    """Check if fricative meets Gate 1 criteria."""
    target = FRICATIVE_TARGETS.get(fricative, {})
    centroid_target = target.get("centroid")
    tolerance = target.get("tolerance_pct")

    if centroid_target is None or tolerance is None:
        return True, ["diffuse/aspiration — no centroid target"]

    measured = moments["centroid_hz"]
    error_pct = abs(measured - centroid_target) / centroid_target * 100
    passed = error_pct <= tolerance

    notes = []
    if not passed:
        notes.append(f"{fricative}: centroid {measured} vs {centroid_target} "
                     f"({error_pct:.1f}% > {tolerance}%)")
    return passed, notes


def demo(sr=SR, duration=0.5, seed=42):
    """Synthesize all fricatives and measure spectral moments."""
    results = {}
    all_pass = True

    for fric in FRICATIVE_SPECS:
        signal = synthesize_fricative(fric, duration=duration, sr=sr, seed=seed)
        moments = measure_spectral_moments(signal, sr=sr)
        passed, notes = check_fricative(fric, moments)

        results[fric] = {
            "moments": moments,
            "passed": passed,
            "notes": notes,
            "voiced": FRICATIVE_SPECS[fric]["voiced"],
        }

        if not passed:
            all_pass = False

        status = "PASS" if passed else "FAIL"
        centroid = moments["centroid_hz"]
        target = FRICATIVE_TARGETS[fric].get("centroid", "diffuse")
        print(f"{fric}: {status}  centroid={centroid} (target={target})  "
              f"spread={moments['spread_hz']}  skew={moments['skew']}  "
              f"{'voiced' if FRICATIVE_SPECS[fric]['voiced'] else 'unvoiced'}")

        # Save audio
        out_dir = os.path.join(os.path.dirname(__file__), "..", "renders")
        os.makedirs(out_dir, exist_ok=True)
        safe_name = fric.strip("/").replace("/", "_")
        wavfile.write(os.path.join(out_dir, f"fricative_{safe_name}.wav"), sr,
                      (signal * 32767).astype(np.int16))

    print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VOICE fricatives")
    parser.add_argument("--demo", action="store_true",
                        help="Synthesize all fricatives")
    parser.add_argument("--sr", type=int, default=SR)
    parser.add_argument("--duration", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.demo:
        results = demo(sr=args.sr, duration=args.duration, seed=args.seed)
        out = os.path.join(os.path.dirname(__file__), "..", "renders",
                           "fricative_measurements.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nMeasurements saved: {out}")

    else:
        parser.print_help()