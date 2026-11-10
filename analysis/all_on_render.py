#!/usr/bin/env python3
"""
VOICE — All-On Render (Phase 3, Gate 2 completion).

Creates renders with all calibrated effects applied:
  - Aperiodicity (raven grain -57 dB, ghost-hiss 0.07 dB shelf)
  - AM family (sub-bass 0.9% + wolf warmth 0.5% = 1.4%)
  - Spectral tilt shaping (-1.30 dB/oct)

Usage:
    python all_on_render.py --apply
"""

import argparse
import json
import os
import sys

import numpy as np
import yaml
from scipy.io import wavfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/adora/narusya-hearing/analysis')

SR = 48000

# Calibrated effect targets
CALIBRATED_TARGETS = {
    "raven_grain": {"band": (1000, 3000), "level_db": -57.0},
    "sibilance": {"band": (5000, 9000), "shelf_db": 0.07},
    "breathiness": {"band": (0, 16000), "level_db": -30.0},
}

SUB_DEPTH = 0.9
WOLF_DEPTH = 0.5
TILT_TARGET = -1.30


def apply_all_effects(signal, sr, f0, seed=42):
    """Apply all calibrated effects to a signal."""
    from aperiodicity import add_aperiodicity
    from am_family import apply_am_family
    from spectral_tilt import measure_tilt, tilt_eq

    # 1. Aperiodicity (raven grain + ghost-hiss + breathiness)
    mixed, noise = add_aperiodicity(signal, sr=sr, targets=CALIBRATED_TARGETS, seed=seed)

    # 2. AM family (sub-bass + wolf warmth)
    am_signal, _, _ = apply_am_family(mixed, sr, f0, sub_depth=SUB_DEPTH,
                                      wolf_depth=WOLF_DEPTH)

    # 3. Spectral tilt shaping
    current_tilt = measure_tilt(am_signal, sr)
    shaped = tilt_eq(am_signal, sr, current_tilt, TILT_TARGET)

    # Normalize
    peak = np.max(np.abs(shaped))
    if peak > 0.95:
        shaped = shaped * (0.95 / peak)

    return shaped


def apply_to_renders(render_dir, output_dir, sr=SR):
    """Apply all effects to all renders."""
    os.makedirs(output_dir, exist_ok=True)
    results = []

    for f in sorted(os.listdir(render_dir)):
        if not f.endswith('.wav'):
            continue
        path = os.path.join(render_dir, f)
        sr_in, signal = wavfile.read(path)
        if signal.dtype != np.float64 and signal.dtype != np.float32:
            signal = signal.astype(np.float64) / 32768.0
        if signal.ndim > 1:
            signal = signal[:, 0]

        # Extract f0 from filename or use default
        f0 = 190.0

        shaped = apply_all_effects(signal, sr_in, f0, seed=42)

        out_path = os.path.join(output_dir, f)
        wavfile.write(out_path, sr_in, (shaped * 32767).astype(np.int16))

        # Measure HNR from HEARING
        sys.path.insert(0, '/home/adora/narusya-hearing/analysis')
        from autonomous_eval import measure_render
        features = measure_render(out_path)
        hnr = features.get('hnr', 0)
        tilt = features.get('tilt', 0)

        results.append({
            "file": f,
            "hnr": float(hnr),
            "tilt": float(tilt),
        })

    return results


def main():
    parser = argparse.ArgumentParser(description="VOICE all-on render")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--input", default="/home/adora/narusya-voice/renders/phase1")
    parser.add_argument("--output", default="/home/adora/narusya-voice/renders/phase3_allon")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.apply:
        results = apply_to_renders(args.input, args.output)
        print(f"Applied all effects to {len(results)} renders")
        print(f"  Output: {args.output}")

        hnrs = [r['hnr'] for r in results]
        tilts = [r['tilt'] for r in results]
        print(f"  HNR: median={np.median(hnrs):.1f}, range=[{min(hnrs):.1f}, {max(hnrs):.1f}]")
        print(f"  Tilt: median={np.median(tilts):.2f}, range=[{min(tilts):.2f}, {max(tilts):.2f}]")

        out_path = os.path.join(os.path.dirname(args.output), "allon_render_report.json")
        with open(out_path, 'w') as f:
            json.dump({"results": results}, f, indent=2)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()