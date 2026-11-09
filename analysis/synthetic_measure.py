#!/usr/bin/env python3
"""
VOICE — Synthetic mode measurement (Round 6, Zarza's proposal)
=============================================================
Instead of using Praat's Burg formant tracker (natural-speech
assumptions that fail on synthetic voices), measure formant energy
within ±5% windows around KNOWN targets. We know what the synth
produced, so we look for it directly.

Gate 0's question: "did the synth produce what the genome asked for?"
For that, we know the targets. Hunting spectral peaks with a
natural-speech tracker imports its failure modes into the gate.
Measuring within target windows answers the question directly.

Keep Praat for natural samples (§3 work) where targets are unknown
and its assumptions are earned.
"""

import numpy as np
from scipy.signal import welch


def measure_formants_synthetic(signal, sr, targets, window_pct=0.05):
    """Measure formants by finding spectral peaks within ±window_pct
    of each known target frequency.

    Returns dict: {formant_name: {median, n_frames, energy_db, peak_hz}}
    """
    n_samples = len(signal)
    # Compute power spectral density
    freqs, psd = welch(signal, fs=sr, nperseg=min(2048, n_samples // 4),
                       noverlap=None, window='hann')
    
    result = {}
    for name, target in targets.items():
        lo = target * (1 - window_pct)
        hi = target * (1 + window_pct)
        mask = (freqs >= lo) & (freqs <= hi)
        if not np.any(mask):
            result[name] = {"median": None, "n": 0, "energy_db": None,
                            "peak_hz": None, "in_window": False}
            continue
        window_freqs = freqs[mask]
        window_psd = psd[mask]
        peak_idx = np.argmax(window_psd)
        peak_hz = window_freqs[peak_idx]
        peak_energy = window_psd[peak_idx]
        # Energy in dB relative to full spectrum peak
        full_peak = np.max(psd)
        energy_db = 10 * np.log10(peak_energy / full_peak) if full_peak > 0 else -99
        # Check if peak is within window (it always is by construction)
        in_window = lo <= peak_hz <= hi
        # Also check: is this a real peak (not just noise floor)?
        # Compare to median energy in the window
        median_energy = np.median(window_psd)
        is_peak = peak_energy > median_energy * 2  # 3 dB above median
        
        result[name] = {
            "median": round(float(peak_hz), 1),
            "n": int(np.sum(mask)),
            "energy_db": round(float(energy_db), 1),
            "peak_hz": round(float(peak_hz), 1),
            "in_window": bool(in_window),
            "is_peak": bool(is_peak),
            "target": target,
            "error_pct": round(abs(peak_hz - target) / target * 100, 1),
        }
    return result


def measure_f0_synthetic(signal, sr, target_f0=190.0, window_hz=10.0):
    """Measure F0 by finding the peak near the target in the low-frequency region."""
    freqs, psd = welch(signal, fs=sr, nperseg=min(4096, len(signal) // 4),
                       noverlap=None, window='hann')
    mask = (freqs >= target_f0 - window_hz) & (freqs <= target_f0 + window_hz)
    if not np.any(mask):
        return {"median": None, "error_hz": None}
    peak_idx = np.argmax(psd[mask])
    peak_hz = freqs[mask][peak_idx]
    return {"median": round(float(peak_hz), 1),
            "error_hz": round(float(abs(peak_hz - target_f0)), 1)}


def gate0_synthetic(measured_formants, target_formants, measured_f0, target_f0,
                    label, jitter_pct=None, shimmer_pct=None):
    """Gate 0 in synthetic mode: check formants within ±5% of known targets."""
    notes, passed = [], True
    
    # F0 check
    if measured_f0["median"] is None or abs(measured_f0["median"] - target_f0) > 3.0:
        passed = False
        notes.append(f"{label}: F0 {measured_f0['median']} vs {target_f0} (±3 Hz)")
    
    # Formant checks
    for name, target in target_formants.items():
        m = measured_formants[name]
        if m["median"] is None:
            passed = False
            notes.append(f"{label}: {name} no peak found in ±5% window")
            continue
        if not m["is_peak"]:
            notes.append(f"{label}: {name} {m['peak_hz']} Hz — weak peak "
                         f"(energy {m['energy_db']} dB below full spectrum peak)")
        if m["error_pct"] > 5.0:
            passed = False
            notes.append(f"{label}: {name} {m['peak_hz']} vs {target} "
                         f"({m['error_pct']}% > 5%)")
    
    # Jitter/shimmer (if provided)
    if jitter_pct is not None and not (0.5 <= jitter_pct <= 0.9):
        notes.append(f"{label}: jitter {jitter_pct}% outside 0.5–0.9%")
    if shimmer_pct is not None and not (3.0 <= shimmer_pct <= 5.0):
        notes.append(f"{label}: shimmer {shimmer_pct}% outside 3–5%")
    
    return passed, notes


def f4_sweep(sr=48000, duration=1.0, f4_values=None):
    """F4 diagnostic sweep: synthesize single-resonator renders at known
    F4 values, measure back with synthetic mode. Tells us if the tracker
    or the synth owns the F4 error.
    
    Returns list of (target_f4, measured_f4, error_pct).
    """
    if f4_values is None:
        f4_values = list(range(2800, 3601, 100))
    
    results = []
    n_samples = int(duration * sr)
    for target_f4 in f4_values:
        # Synthesize a single resonator at target_f4
        freqs = np.arange(n_samples) / sr
        # Simple sine wave at target_f4 with some harmonics
        signal = (np.sin(2 * np.pi * target_f4 * freqs) +
                  0.5 * np.sin(2 * np.pi * 2 * target_f4 * freqs) +
                  0.25 * np.sin(2 * np.pi * 3 * target_f4 * freqs))
        # Add a low-frequency carrier (F0 ~ 190) to make it voice-like
        signal += 0.3 * np.sin(2 * np.pi * 190 * freqs)
        signal = signal / np.max(np.abs(signal)) * 0.5
        
        measured = measure_formants_synthetic(signal, sr, {"F4": target_f4})
        m = measured["F4"]
        results.append({
            "target_f4": target_f4,
            "measured_f4": m["median"],
            "error_pct": m["error_pct"],
            "is_peak": m["is_peak"],
            "energy_db": m["energy_db"],
        })
    return results


if __name__ == "__main__":
    # Quick test
    import sys
    sys.path.insert(0, '.')
    
    # Generate a test signal with known formants
    sr = 48000
    duration = 1.0
    n = int(duration * sr)
    t = np.arange(n) / sr
    # Simulate a vowel with F1=450, F2=1500, F3=2770, F4=3100
    signal = (0.5 * np.sin(2 * np.pi * 450 * t) +
              0.3 * np.sin(2 * np.pi * 1500 * t) +
              0.2 * np.sin(2 * np.pi * 2770 * t) +
              0.1 * np.sin(2 * np.pi * 3100 * t))
    signal = signal / np.max(np.abs(signal)) * 0.5
    
    targets = {"F1": 450, "F2": 1500, "F3": 2770, "F4": 3100}
    measured = measure_formants_synthetic(signal, sr, targets)
    for name, m in measured.items():
        print(f"{name}: target={m['target']}, measured={m['median']}, "
              f"error={m['error_pct']}%, is_peak={m['is_peak']}, energy={m['energy_db']} dB")
    
    print("\nF4 sweep:")
    sweep = f4_sweep(sr, 0.5, list(range(2900, 3301, 100)))
    for r in sweep:
        print(f"  target={r['target_f4']}, measured={r['measured_f4']}, "
              f"error={r['error_pct']}%, peak={r['is_peak']}")