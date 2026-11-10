#!/usr/bin/env python3
"""
VOICE — Spectral Tilt Shaping (Phase 3, Gate 2 completion).

Post-processing spectral tilt filter that shapes the spectral slope
to match the genome's measured tilt target (-1.30 dB/oct true).

The tilt EQ (also called "spectral tilt filter") adjusts the spectral
slope by applying a frequency-dependent gain:

    gain_db(f) = (target_tilt - current_tilt) * log2(f / f_ref)

This is applied as an FFT-based filter (zero-phase) to avoid phase
distortion.

Usage:
    python spectral_tilt.py --demo     # show tilt before/after
    python spectral_tilt.py --apply    # apply to renders
    python spectral_tilt.py --verify   # verify target met
"""

import argparse
import json
import os
import sys

import numpy as np
import yaml
from scipy.io import wavfile
from scipy.signal import get_window

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/adora/narusya-hearing/analysis')

SR = 48000
TILT_TARGET_DB_OCT = -1.30  # genome measured tilt (true dB/oct)
F_REF = 1000.0  # reference frequency for tilt EQ


def measure_tilt(signal, sr, f_lo=100, f_hi=4000):
    """Measure spectral tilt via Welch PSD (matching HEARING's instrument)."""
    from scipy.signal import welch
    freqs, psd = welch(signal, fs=sr, nperseg=min(4096, len(signal)),
                       noverlap=min(2048, len(signal)//2))
    mask = (freqs >= f_lo) & (freqs <= f_hi)
    f_band = freqs[mask]
    psd_band = psd[mask]
    # Linear fit in log-log space: slope = dB/oct
    log_f = np.log10(f_band[f_band > 0])
    log_psd = 10 * np.log10(psd_band[f_band > 0] + 1e-20)
    # Fit line: log_psd = slope * log_f + intercept
    # slope in dB/decade; convert to dB/oct by × log10(2)
    coeffs = np.polyfit(log_f, log_psd, 1)
    slope_db_decade = coeffs[0]
    slope_db_oct = slope_db_decade * np.log10(2)
    return slope_db_oct


def tilt_eq(signal, sr, current_tilt, target_tilt, f_ref=F_REF):
    """Apply spectral tilt EQ to change spectral slope.

    gain_db(f) = (target_tilt - current_tilt) * log2(f / f_ref)

    Applied as FFT multiply (zero-phase).
    """
    n = len(signal)
    # FFT
    spectrum = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)

    # Compute gain per frequency bin
    tilt_diff = target_tilt - current_tilt  # dB/oct change needed
    gain_db = np.zeros_like(freqs)
    for i, f in enumerate(freqs):
        if f > 0:
            gain_db[i] = tilt_diff * np.log2(f / f_ref)
        else:
            gain_db[i] = 0

    # Convert to linear
    gain_linear = 10 ** (gain_db / 20.0)

    # Apply
    spectrum_shaped = spectrum * gain_linear

    # IFFT
    signal_shaped = np.fft.irfft(spectrum_shaped, n=n)

    return signal_shaped


def apply_to_renders(render_dir, output_dir, sr=SR):
    """Apply tilt shaping to all renders in a directory."""
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

        # Measure current tilt
        current_tilt = measure_tilt(signal, sr_in)

        # Apply tilt EQ
        shaped = tilt_eq(signal, sr_in, current_tilt, TILT_TARGET_DB_OCT)

        # Measure new tilt
        new_tilt = measure_tilt(shaped, sr_in)

        # Normalize to prevent clipping
        peak = np.max(np.abs(shaped))
        if peak > 0.95:
            shaped = shaped * (0.95 / peak)

        # Save
        out_path = os.path.join(output_dir, f)
        wavfile.write(out_path, sr_in, (shaped * 32767).astype(np.int16))

        results.append({
            "file": f,
            "tilt_before": float(current_tilt),
            "tilt_after": float(new_tilt),
            "tilt_target": TILT_TARGET_DB_OCT,
        })

    return results


def demo(sr=SR):
    """Demo: show tilt before/after on a single render."""
    render_path = '/home/adora/narusya-voice/renders/phase1/ɑ.wav'
    sr_in, signal = wavfile.read(render_path)
    if signal.dtype != np.float64:
        signal = signal.astype(np.float64) / 32768.0
    if signal.ndim > 1:
        signal = signal[:, 0]

    current = measure_tilt(signal, sr_in)
    shaped = tilt_eq(signal, sr_in, current, TILT_TARGET_DB_OCT)
    new = measure_tilt(shaped, sr_in)

    print(f"Spectral Tilt Shaping Demo")
    print(f"  Render: ɑ.wav")
    print(f"  Before: {current:.2f} dB/oct")
    print(f"  Target: {TILT_TARGET_DB_OCT:.2f} dB/oct")
    print(f"  After:  {new:.2f} dB/oct")
    print(f"  Error:  {abs(new - TILT_TARGET_DB_OCT):.2f} dB/oct")


def main():
    parser = argparse.ArgumentParser(description="VOICE spectral tilt shaping")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--input", default="/home/adora/narusya-voice/renders/phase1")
    parser.add_argument("--output", default="/home/adora/narusya-voice/renders/phase1_shaped")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.demo:
        demo()

    elif args.apply:
        results = apply_to_renders(args.input, args.output)
        print(f"Applied tilt shaping to {len(results)} renders")
        print(f"  Output: {args.output}")
        tilts_before = [r['tilt_before'] for r in results]
        tilts_after = [r['tilt_after'] for r in results]
        print(f"  Tilt before: median={np.median(tilts_before):.2f}")
        print(f"  Tilt after:  median={np.median(tilts_after):.2f}")
        print(f"  Target:      {TILT_TARGET_DB_OCT:.2f}")

        # Save report
        out_path = os.path.join(os.path.dirname(args.output), "spectral_tilt_report.json")
        with open(out_path, 'w') as f:
            json.dump({"target": TILT_TARGET_DB_OCT, "results": results}, f, indent=2)

    elif args.verify:
        # Check shaped renders
        results = []
        for f in sorted(os.listdir(args.output)):
            if f.endswith('.wav'):
                path = os.path.join(args.output, f)
                sr_in, signal = wavfile.read(path)
                if signal.dtype != np.float64:
                    signal = signal.astype(np.float64) / 32768.0
                if signal.ndim > 1:
                    signal = signal[:, 0]
                t = measure_tilt(signal, sr_in)
                results.append(t)
        print(f"Shaped renders tilt: median={np.median(results):.2f}, range=[{min(results):.2f}, {max(results):.2f}]")
        print(f"Target: {TILT_TARGET_DB_OCT:.2f}")
        err = abs(np.median(results) - TILT_TARGET_DB_OCT)
        print(f"Error: {err:.2f} dB/oct")
        print(f"Verify: {'PASS' if err < 0.5 else 'FAIL'}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()