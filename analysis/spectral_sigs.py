#!/usr/bin/env python3
"""
VOICE — Spectral signatures subsystem (Phase 3, Step 3).

Raven grain (low-mid band aperiodicity, 1000-3000 Hz) and ghost-of-a-hiss
(/s/ level restraint, centroid untouched). Steady-state calibrations on
sustained material.

Calibration protocol (§2 of Round 10 brief):
- Depth ladder: render at depths 0→max in steps, measure HEARING
  discrimination. Set genome at ~70% of detection threshold.

Usage:
    python spectral_sigs.py --ladder-raven   # raven grain depth ladder
    python spectral_sigs.py --ladder-hiss    # ghost-hiss depth ladder
    python spectral_sigs.py --demo           # render with signatures
"""

import argparse
import json
import os
import sys

import numpy as np
from scipy.signal import lfilter, butter, filtfilt
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 48000

# Genome proposal values
RAVEN_BAND = (1000, 3000)
RAVEN_LEVEL_DB = -24  # ≈6% of harmonic level
HISSE_SHELF_DB = (2, 3)  # 2-3 dB shelf
HISSE_BAND = (5000, 9000)


def band_noise(signal, sr, band, level_db, seed=42):
    """Add band-limited noise at specified level.

    Used for raven grain (low-mid aperiodicity) and ghost-hiss.
    """
    rng = np.random.default_rng(seed)
    n = len(signal)
    noise = rng.normal(0, 1, n)

    # Bandpass filter
    nyq = sr / 2
    low = band[0] / nyq
    high = min(band[1] / nyq, 0.99)
    b, a = butter(4, [low, high], btype='band')
    filtered = filtfilt(b, a, noise)

    # Scale to level
    level_linear = 10 ** (level_db / 20.0)
    filtered = filtered * level_linear

    # Mix into signal (additive)
    return signal + filtered


def sibilance_shelf(signal, sr, band, shelf_db, seed=42):
    """Apply a high-shelf boost in the sibilance band.

    Ghost of a hiss: subtle shelf boost, centroid untouched.
    """
    rng = np.random.default_rng(seed)
    n = len(signal)

    # Generate shaped noise in the band
    noise = rng.normal(0, 1, n)
    nyq = sr / 2
    low = band[0] / nyq
    high = min(band[1] / nyq, 0.99)
    b, a = butter(4, [low, high], btype='band')
    filtered = filtfilt(b, a, noise)

    # Shelf boost
    level = 10 ** (shelf_db / 20.0)
    filtered = filtered * level * 0.1  # subtle: 10% of shelf level

    return signal + filtered


def raven_grain_depth_ladder(genome, vowel="ɑ", f0=190.0, duration=2.0,
                             seed=42, sr=SR):
    """Depth ladder for raven grain calibration."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from phase1_synth import load_genome, make_source, synthesize_vowel
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "narusya-hearing", "analysis"))
    from autonomous_eval import measure_render

    genome = load_genome(os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml"))

    rng = np.random.default_rng(seed)
    source = make_source(genome, f0, duration, "lf", rng)
    anchor = genome["filter"]["neutral_anchor"]
    grid = genome["vowel_grid"][vowel]
    formants = {"F1": grid[0], "F2": grid[1], "F3": grid[2], "F4": anchor["F4"]["hz"]}
    bandwidths = {k: anchor[k]["bw"] for k in ["F1", "F2", "F3", "F4"] if k in anchor and isinstance(anchor[k], dict)}
    clean = synthesize_vowel(f0, formants, duration, sr, source=source, bandwidths=bandwidths)

    out_dir = os.path.join(os.path.dirname(__file__), "..", "renders", "spectral_sigs")
    os.makedirs(out_dir, exist_ok=True)

    # Depth ladder: level_db from -40 to -12 in steps
    levels = [-40, -36, -32, -28, -24, -20, -16, -12]
    results = []

    for level in levels:
        if level == -40:  # effectively clean
            sig = clean.copy()
        else:
            sig = band_noise(clean.copy(), sr, RAVEN_BAND, level, seed=seed)

        fname = f"raven_level_{level}.wav"
        fpath = os.path.join(out_dir, fname)
        from scipy.io import wavfile
        wavfile.write(fpath, sr, (sig * 32767).astype(np.int16))

        try:
            meas = measure_render(fpath)
        except Exception as e:
            meas = {"error": str(e)}

        results.append({
            "level_db": level,
            "measurements": meas,
        })
        print(f"level={level:3d} dB  tilt={meas.get('tilt', 'N/A')}  hnr={meas.get('hnr', 'N/A')}  mfcc[0]={meas.get('mfcc', [0])[0] if meas.get('mfcc') else 'N/A'}")

    return results


def hiss_depth_ladder(genome, vowel="ɑ", f0=190.0, duration=2.0,
                      seed=42, sr=SR):
    """Depth ladder for ghost-of-a-hiss calibration."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from phase1_synth import load_genome, make_source, synthesize_vowel
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "narusya-hearing", "analysis"))
    from autonomous_eval import measure_render

    genome = load_genome(os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml"))

    rng = np.random.default_rng(seed)
    source = make_source(genome, f0, duration, "lf", rng)
    anchor = genome["filter"]["neutral_anchor"]
    grid = genome["vowel_grid"][vowel]
    formants = {"F1": grid[0], "F2": grid[1], "F3": grid[2], "F4": anchor["F4"]["hz"]}
    bandwidths = {k: anchor[k]["bw"] for k in ["F1", "F2", "F3", "F4"] if k in anchor and isinstance(anchor[k], dict)}
    clean = synthesize_vowel(f0, formants, duration, sr, source=source, bandwidths=bandwidths)

    out_dir = os.path.join(os.path.dirname(__file__), "..", "renders", "spectral_sigs")
    os.makedirs(out_dir, exist_ok=True)

    # Shelf levels: 0 (clean), 0.5, 1.0, 1.5, 2.0, 2.5, 3.0 dB
    levels = [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    results = []

    for level in levels:
        if level == 0:
            sig = clean.copy()
        else:
            sig = sibilance_shelf(clean.copy(), sr, HISSE_BAND, level, seed=seed)

        fname = f"hiss_shelf_{level}.wav"
        fpath = os.path.join(out_dir, fname)
        from scipy.io import wavfile
        wavfile.write(fpath, sr, (sig * 32767).astype(np.int16))

        try:
            meas = measure_render(fpath)
        except Exception as e:
            meas = {"error": str(e)}

        results.append({
            "shelf_db": level,
            "measurements": meas,
        })
        print(f"shelf={level:.1f} dB  tilt={meas.get('tilt', 'N/A')}  hnr={meas.get('hnr', 'N/A')}")

    return results


def demo(genome, vowel="ɑ", f0=190.0, duration=2.0, seed=42, sr=SR):
    """Render with spectral signatures at calibrated depths."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from phase1_synth import load_genome, make_source, synthesize_vowel

    rng = np.random.default_rng(seed)
    source = make_source(genome, f0, duration, "lf", rng)
    anchor = genome["filter"]["neutral_anchor"]
    grid = genome["vowel_grid"][vowel]
    formants = {"F1": grid[0], "F2": grid[1], "F3": grid[2], "F4": anchor["F4"]["hz"]}
    bandwidths = {k: anchor[k]["bw"] for k in ["F1", "F2", "F3", "F4"] if k in anchor and isinstance(anchor[k], dict)}
    clean = synthesize_vowel(f0, formants, duration, sr, source=source, bandwidths=bandwidths)

    # Apply raven grain at calibrated depth (-24 dB)
    raven_sig = band_noise(clean.copy(), sr, RAVEN_BAND, -24, seed=seed)

    # Apply ghost-hiss at calibrated depth (2.5 dB shelf midpoint)
    hiss_sig = sibilance_shelf(clean.copy(), sr, HISSE_BAND, 2.5, seed=seed)

    # Both
    both_sig = band_noise(clean.copy(), sr, RAVEN_BAND, -24, seed=seed)
    both_sig = sibilance_shelf(both_sig, sr, HISSE_BAND, 2.5, seed=seed)

    out_dir = os.path.join(os.path.dirname(__file__), "..", "renders", "spectral_sigs")
    os.makedirs(out_dir, exist_ok=True)
    from scipy.io import wavfile
    wavfile.write(os.path.join(out_dir, "sig_clean.wav"), sr, (clean * 32767).astype(np.int16))
    wavfile.write(os.path.join(out_dir, "sig_raven.wav"), sr, (raven_sig * 32767).astype(np.int16))
    wavfile.write(os.path.join(out_dir, "sig_hiss.wav"), sr, (hiss_sig * 32767).astype(np.int16))
    wavfile.write(os.path.join(out_dir, "sig_both.wav"), sr, (both_sig * 32767).astype(np.int16))

    print("Saved: sig_clean.wav, sig_raven.wav, sig_hiss.wav, sig_both.wav")
    return clean, raven_sig, hiss_sig, both_sig


def main():
    parser = argparse.ArgumentParser(description="VOICE spectral signatures")
    parser.add_argument("--ladder-raven", action="store_true", help="Raven grain depth ladder")
    parser.add_argument("--ladder-hiss", action="store_true", help="Ghost-hiss depth ladder")
    parser.add_argument("--demo", action="store_true", help="Render with signatures")
    parser.add_argument("--vowel", default="ɑ")
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sr", type=int, default=SR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    with open(genome_path) as f:
        genome = yaml.safe_load(f)

    if args.ladder_raven:
        results = raven_grain_depth_ladder(genome, vowel=args.vowel, duration=args.duration,
                                           seed=args.seed, sr=args.sr)
        if args.json:
            print(json.dumps(results, indent=2))
        out_path = os.path.join(os.path.dirname(__file__), "..", "renders",
                                "spectral_sigs", "raven_ladder.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)

    elif args.ladder_hiss:
        results = hiss_depth_ladder(genome, vowel=args.vowel, duration=args.duration,
                                    seed=args.seed, sr=args.sr)
        if args.json:
            print(json.dumps(results, indent=2))
        out_path = os.path.join(os.path.dirname(__file__), "..", "renders",
                                "spectral_sigs", "hiss_ladder.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)

    elif args.demo:
        demo(genome, vowel=args.vowel, duration=args.duration, seed=args.seed, sr=args.sr)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()