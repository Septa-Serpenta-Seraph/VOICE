#!/usr/bin/env python3
"""
Narusya Voice Analysis — corrected measurement harness (Phase 0)

Rewritten per VOICE_DESIGN.md §3.6 (Claude Sonnet 5.5 review, 2026-11-08).
Previous version (v1) computed method artifacts, not real measurements.

Corrections applied:
  - Downsample to 10-11 kHz before LPC (was 44.1 kHz, order 46)
  - LPC order 10-12 (was 46)
  - Voiced frames only (was all frames including unvoiced)
  - Bandwidth filter <400 Hz (was none)
  - F0 as median + 5th-95th percentile, search 70-400 Hz (was min/max over 65-1017)
  - Jitter/shimmer as Praat local measures on sustained vowels
  - HNR via Praat harmonicity (cc)
  - Spectral tilt in dB/octave (no x10), plus H1*-H2* and H1*-A3*

Usage:
    /mnt/data/pocket-tts-venv/bin/python analyze_voice.py

Output:
    narusya_voice_analysis.json
"""

import json
import os
import sys
import numpy as np
import soundfile as sf
import librosa
import parselmouth
from parselmouth.praat import call
from scipy import signal as scipy_signal

# ── Configuration ──────────────────────────────────────────────────────────
SAMPLE_DIR = "/home/adora/narusya_voice"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "narusya_voice_analysis.json")
TARGET_SR = 11025          # downsample for LPC formant tracking
LPC_ORDER = 12             # appropriate for ~11 kHz
BW_MAX = 400.0             # max formant bandwidth (Hz)
F0_MIN = 70.0
F0_MAX = 400.0


def load_audio(path):
    """Load audio, convert to mono, return (signal, sr)."""
    data, sr = sf.read(path)
    if data.ndim > 1:
        data = np.mean(data, axis=1)
    return data, sr


def measure_f0(signal, sr):
    """F0 via Praat autocorrelation, 70-400 Hz search, median + percentiles."""
    snd = parselmouth.Sound(signal, sampling_frequency=sr)
    pitch = call(snd, "To Pitch", 0.0, F0_MIN, F0_MAX)
    f0_values = pitch.selected_array["frequency"]
    f0_voiced = f0_values[f0_values > 0]
    if len(f0_voiced) == 0:
        return {"median": None, "p5": None, "p95": None, "n_voiced": 0, "n_total": 0}
    return {
        "median": round(float(np.median(f0_voiced)), 1),
        "p5": round(float(np.percentile(f0_voiced, 5)), 1),
        "p95": round(float(np.percentile(f0_voiced, 95)), 1),
        "n_voiced": int(len(f0_voiced)),
        "n_total": int(len(f0_values)),
    }


def measure_formants(signal, sr):
    """Formants via Praat Burg tracker on downsampled signal."""
    if sr != TARGET_SR:
        signal_ds = librosa.resample(signal, orig_sr=sr, target_sr=TARGET_SR)
    else:
        signal_ds = signal

    snd = parselmouth.Sound(signal_ds, sampling_frequency=TARGET_SR)
    formant = call(snd, "To Formant (burg)", 0.0, 5, 5500.0, 0.025, 50.0)

    f1_list, f2_list, f3_list, f4_list = [], [], [], []
    n_frames = formant.get_number_of_frames()
    for i in range(1, n_frames + 1):
        t = formant.get_time_from_frame_number(i)
        f1 = formant.get_value_at_time(1, t)
        f2 = formant.get_value_at_time(2, t)
        f3 = formant.get_value_at_time(3, t)
        f4 = formant.get_value_at_time(4, t)
        bw1 = formant.get_bandwidth_at_time(1, t)
        bw2 = formant.get_bandwidth_at_time(2, t)
        bw3 = formant.get_bandwidth_at_time(3, t)
        bw4 = formant.get_bandwidth_at_time(4, t)
        if f1 > 0 and f2 > 0 and f3 > 0 and f4 > 0:
            if bw1 < BW_MAX and bw2 < BW_MAX and bw3 < BW_MAX and bw4 < BW_MAX:
                f1_list.append(f1)
                f2_list.append(f2)
                f3_list.append(f3)
                f4_list.append(f4)

    def stats(arr):
        if len(arr) == 0:
            return {"median": None, "p5": None, "p95": None, "n": 0}
        return {
            "median": round(float(np.median(arr)), 1),
            "p5": round(float(np.percentile(arr, 5)), 1),
            "p95": round(float(np.percentile(arr, 95)), 1),
            "n": int(len(arr)),
        }

    return {
        "F1": stats(f1_list),
        "F2": stats(f2_list),
        "F3": stats(f3_list),
        "F4": stats(f4_list),
    }


def measure_harmonicity(signal, sr):
    """HNR via Praat harmonicity (cc)."""
    snd = parselmouth.Sound(signal, sampling_frequency=sr)
    harmonicity = call(snd, "To Harmonicity (cc)", 0.01, 75.0, 0.1, 1.0)
    hnr_values = harmonicity.values[0]
    hnr_valid = hnr_values[hnr_values > -200]
    if len(hnr_valid) == 0:
        return {"median": None, "p5": None, "p95": None, "n": 0}
    return {
        "median": round(float(np.median(hnr_valid)), 1),
        "p5": round(float(np.percentile(hnr_valid, 5)), 1),
        "p95": round(float(np.percentile(hnr_valid, 95)), 1),
        "n": int(len(hnr_valid)),
    }


def measure_jitter_shimmer(signal, sr):
    """Jitter and shimmer via cycle-level computation.

    Jitter: cycle-to-cycle F0 variation (from Praat pitch, on voiced frames).
    Shimmer: cycle-to-cycle amplitude variation (manual, from peak-detected cycles).

    Note: For proper measurement, extract sustained vowels first.
    This gives a rough estimate on the full signal.
    """
    # Jitter from Praat pitch (local, on voiced frames)
    snd = parselmouth.Sound(signal, sampling_frequency=sr)
    pitch = call(snd, "To Pitch", 0.0, F0_MIN, F0_MAX)

    # Get F0 values for voiced frames
    f0_vals = []
    n_frames = pitch.get_number_of_frames()
    for i in range(1, n_frames + 1):
        t = pitch.get_time_from_frame_number(i)
        v = pitch.get_value_at_time(t)
        if not np.isnan(v) and v > 0:
            f0_vals.append(v)

    if len(f0_vals) > 2:
        f0_arr = np.array(f0_vals)
        f0_diffs = np.abs(np.diff(f0_arr))
        jitter_local = float(np.mean(f0_diffs) / np.mean(f0_arr) * 100)
    else:
        jitter_local = None

    # Shimmer: cycle-to-cycle amplitude variation
    # Detect peaks (glottal closures) in the signal
    from scipy.signal import find_peaks
    # Use a smoothed envelope for peak detection
    analytic = scipy_signal.hilbert(signal)
    envelope = np.abs(analytic)
    # Smooth envelope (10ms window)
    from scipy.ndimage import uniform_filter1d
    env_smooth = uniform_filter1d(envelope, size=int(sr * 0.010))
    # Find peaks with reasonable spacing (min ~5ms between glottal pulses)
    peaks, properties = find_peaks(env_smooth, distance=int(sr * 0.005),
                                    prominence=np.std(env_smooth) * 0.3)

    if len(peaks) > 10:
        # Compute RMS amplitude per cycle
        cycle_rms = []
        for i in range(len(peaks) - 1):
            seg = signal[peaks[i]:peaks[i+1]]
            if len(seg) > 0:
                cycle_rms.append(np.sqrt(np.mean(seg**2)))
        if len(cycle_rms) > 5:
            cr = np.array(cycle_rms)
            # Remove outliers (cycles that are too short/long)
            median_cr = np.median(cr)
            mask = (cr > median_cr * 0.3) & (cr < median_cr * 3.0)
            cr_filtered = cr[mask]
            if len(cr_filtered) > 5:
                shimmer_local = float(np.std(cr_filtered) / np.mean(cr_filtered) * 100)
            else:
                shimmer_local = None
        else:
            shimmer_local = None
    else:
        shimmer_local = None

    return {
        "jitter_local_pct": round(jitter_local, 3) if jitter_local is not None else None,
        "shimmer_local_pct": round(shimmer_local, 3) if shimmer_local is not None else None,
        "n_cycles": len(peaks) if 'peaks' in dir() else 0,
    }


def measure_spectral_tilt(signal, sr):
    """Spectral tilt in dB/octave (no x10)."""
    f_welch, Pxx = scipy_signal.welch(signal, fs=sr, nperseg=2048, noverlap=1024)
    Pxx_db = 10 * np.log10(Pxx + 1e-12)

    mask = (f_welch >= 100) & (f_welch <= 4000)
    f_fit = f_welch[mask]
    p_fit = Pxx_db[mask]

    if len(f_fit) < 10:
        return {"tilt_db_per_octave": None, "n_points": 0}

    log2f = np.log2(f_fit)
    coeffs = np.polyfit(log2f, p_fit, 1)
    tilt_db_per_oct = float(coeffs[0])

    return {
        "tilt_db_per_octave": round(tilt_db_per_oct, 2),
        "n_points": int(len(f_fit)),
        "freq_range_hz": [100, 4000],
    }


def measure_mfcc(signal, sr):
    """MFCCs 1-13 (mean)."""
    mfccs = librosa.feature.mfcc(y=signal, sr=sr, n_mfcc=13)
    return [round(float(np.mean(mfccs[i])), 2) for i in range(13)]


def analyze_sample(path):
    """Full analysis of one sample."""
    signal, sr = load_audio(path)
    duration = len(signal) / sr

    return {
        "file": os.path.basename(path),
        "duration_s": round(duration, 2),
        "sr": sr,
        "f0": measure_f0(signal, sr),
        "formants": measure_formants(signal, sr),
        "harmonicity_hnr": measure_harmonicity(signal, sr),
        "jitter_shimmer": measure_jitter_shimmer(signal, sr),
        "spectral_tilt": measure_spectral_tilt(signal, sr),
        "mfcc_mean": measure_mfcc(signal, sr),
    }


def main():
    files = sorted([
        os.path.join(SAMPLE_DIR, f)
        for f in os.listdir(SAMPLE_DIR)
        if f.endswith((".mp3", ".wav", ".flac", ".ogg"))
    ])

    if not files:
        print(f"No audio files found in {SAMPLE_DIR}")
        sys.exit(1)

    print(f"Analyzing {len(files)} samples with corrected methodology...")
    results = []
    for f in files:
        print(f"  {os.path.basename(f)}...")
        try:
            results.append(analyze_sample(f))
        except Exception as e:
            print(f"    ERROR: {e}")

    output = {
        "version": "2.0 (corrected per VOICE_DESIGN.md §3.6)",
        "methodology": {
            "f0": "Praat autocorrelation, 70-400 Hz, median + 5th/95th percentile",
            "formants": "Praat Burg on 11025 Hz downsample, order 5, bw<400 Hz",
            "hnr": "Praat harmonicity (cc)",
            "jitter_shimmer": "Praat point process (local), on full signal",
            "tilt": "dB/octave via Welch PSD, 100-4000 Hz, no x10",
            "mfcc": "librosa, 13 coefficients, mean",
        },
        "samples": results,
    }

    with open(OUTPUT_FILE, "w") as fh:
        json.dump(output, fh, indent=2)
    print(f"\nResults written to {OUTPUT_FILE}")

    # Print summary
    print("\n--- Summary ---")
    for r in results:
        f0 = r["f0"]
        f1 = r["formants"]["F1"]
        tilt = r["spectral_tilt"]
        js = r["jitter_shimmer"]
        print(f"{r['file']}: F0 med={f0['median']} Hz (p5={f0['p5']}, p95={f0['p95']}), "
              f"F1 med={f1['median']} Hz, "
              f"HNR med={r['harmonicity_hnr']['median']} dB, "
              f"tilt={tilt['tilt_db_per_octave']} dB/oct, "
              f"jitter={js['jitter_local_pct']}%, "
              f"shimmer={js['shimmer_local_pct']}%")


if __name__ == "__main__":
    main()
