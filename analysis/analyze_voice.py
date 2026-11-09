#!/usr/bin/env python3
"""Narusya Voice Analysis — extract acoustic fingerprint from existing samples.

Run with: /mnt/data/pocket-tts-venv/bin/python analyze_voice.py
"""
import os, sys, json, warnings
warnings.filterwarnings("ignore")

import numpy as np
import librosa
import soundfile as sf
from scipy import signal
from scipy.signal import find_peaks

SAMPLES_DIR = "/home/adora/narusya_voice"
OUTPUT_FILE = "/home/adora/.hermes/creative/narusya_voice_analysis.json"

# Best source samples (from skill doc)
CANDIDATES = ["nar_warm.mp3", "nar_new_v1.mp3", "nar_new_v2.mp3",
              "nar_new_v3.mp3", "nar_calm.mp3", "last_voice.mp3",
              "nar_first_words.mp3", "nar_v3_audiotags.mp3"]

def analyze_sample(path):
    """Extract comprehensive acoustic features from an audio file."""
    y, sr = librosa.load(path, sr=None, mono=True)
    duration = len(y) / sr
    
    # Trim silence
    y_trimmed, _ = librosa.effects.trim(y, top_db=20)
    
    # --- F0 (Fundamental Frequency / Pitch) ---
    f0, voiced_flag, voiced_prob = librosa.pyin(
        y_trimmed, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C6'),
        sr=sr, frame_length=2048
    )
    f0_voiced = f0[~np.isnan(f0)]
    f0_mean = float(np.mean(f0_voiced)) if len(f0_voiced) > 0 else 0
    f0_std = float(np.std(f0_voiced)) if len(f0_voiced) > 0 else 0
    f0_min = float(np.min(f0_voiced)) if len(f0_voiced) > 0 else 0
    f0_max = float(np.max(f0_voiced)) if len(f0_voiced) > 0 else 0
    
    # Jitter: cycle-to-cycle F0 variation (approximate from F0 contour)
    if len(f0_voiced) > 2:
        f0_diffs = np.abs(np.diff(f0_voiced))
        jitter = float(np.mean(f0_diffs) / f0_mean * 100) if f0_mean > 0 else 0
    else:
        jitter = 0
    
    # --- Spectral Features ---
    stft = np.abs(librosa.stft(y_trimmed, n_fft=2048, hop_length=512))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    spectrum_mean = np.mean(stft, axis=1)
    
    # Spectral centroid
    centroid = librosa.feature.spectral_centroid(y=y_trimmed, sr=sr)
    centroid_mean = float(np.mean(centroid))
    
    # Spectral rolloff (85%)
    rolloff = librosa.feature.spectral_rolloff(y=y_trimmed, sr=sr, roll_percent=0.85)
    rolloff_mean = float(np.mean(rolloff))
    
    # Spectral bandwidth
    bandwidth = librosa.feature.spectral_bandwidth(y=y_trimmed, sr=sr)
    bandwidth_mean = float(np.mean(bandwidth))
    
    # --- Formant Estimation (LPC) ---
    # Use LPC to estimate formants
    order = int(sr / 1000) + 2  # typical: sr/1000 + 2
    # Frame-based LPC
    frame_length = int(0.025 * sr)  # 25ms
    hop = int(0.010 * sr)  # 10ms
    frames = librosa.util.frame(y_trimmed, frame_length=frame_length, hop_length=hop)
    
    formants_all = {1: [], 2: [], 3: [], 4: []}
    for i in range(frames.shape[1]):
        frame = frames[:, i] * np.hamming(frame_length)
        # LPC
        try:
            a = librosa.lpc(frame, order=order)
            # Find roots
            roots = np.roots(a)
            # Keep roots inside unit circle
            roots = roots[np.abs(roots) < 1]
            # Convert to frequencies
            angles = np.arctan2(roots.imag, roots.real)
            freqs_formant = angles * sr / (2 * np.pi)
            freqs_formant = np.sort(freqs_formant[freqs_formant > 0])
            # Assign to F1-F4
            idx = 0
            for f in freqs_formant:
                if 200 < f < 5000 and idx < 4:
                    formants_all[idx + 1].append(f)
                    idx += 1
        except Exception:
            pass
    
    formant_means = {}
    for k in [1, 2, 3, 4]:
        vals = formants_all[k]
        if vals:
            formant_means[f"F{k}"] = float(np.median(vals))
            formant_means[f"F{k}_std"] = float(np.std(vals))
            formant_means[f"F{k}_min"] = float(np.min(vals))
            formant_means[f"F{k}_max"] = float(np.max(vals))
        else:
            formant_means[f"F{k}"] = 0
    
    # --- MFCCs (timbre fingerprint) ---
    mfccs = librosa.feature.mfcc(y=y_trimmed, sr=sr, n_mfcc=13)
    mfcc_means = [float(np.mean(mfccs[i])) for i in range(13)]
    mfcc_stds = [float(np.std(mfccs[i])) for i in range(13)]
    
    # --- Spectral Tilt (slope of spectrum) ---
    # Fit line to log spectrum
    log_spectrum = 20 * np.log10(spectrum_mean + 1e-10)
    # Use frequencies 100-4000 Hz
    mask = (freqs >= 100) & (freqs <= 4000)
    if np.sum(mask) > 10:
        slope, intercept = np.polyfit(np.log10(freqs[mask]), log_spectrum[mask], 1)
        spectral_tilt = float(slope * 10)  # dB per decade-ish
    else:
        spectral_tilt = 0
    
    # --- Harmonic-to-Noise Ratio (HNR) / breathiness estimate ---
    # Use librosa's harmonic/percussive separation
    harmonic, percussive = librosa.effects.hpss(y_trimmed)
    h_energy = np.sum(harmonic**2)
    p_energy = np.sum(percussive**2)
    hnr = float(10 * np.log10(h_energy / (p_energy + 1e-10))) if p_energy > 0 else 60
    
    # --- Shimmer (amplitude variation) ---
    # Approximate from RMS energy per frame
    rms = librosa.feature.rms(y=y_trimmed, frame_length=frame_length, hop_length=hop)[0]
    if len(rms) > 2:
        rms_diffs = np.abs(np.diff(rms))
        shimmer = float(np.mean(rms_diffs) / np.mean(rms) * 100) if np.mean(rms) > 0 else 0
    else:
        shimmer = 0
    
    # --- Zero Crossing Rate (roughness indicator) ---
    zcr = librosa.feature.zero_crossing_rate(y_trimmed)
    zcr_mean = float(np.mean(zcr))
    
    result = {
        "file": os.path.basename(path),
        "duration_sec": round(duration, 2),
        "trimmed_duration_sec": round(len(y_trimmed) / sr, 2),
        "sample_rate": int(sr),
        "f0": {
            "mean_hz": round(f0_mean, 1),
            "std_hz": round(f0_std, 1),
            "min_hz": round(f0_min, 1),
            "max_hz": round(f0_max, 1),
            "range_hz": round(f0_max - f0_min, 1),
            "voiced_ratio": round(float(np.mean(~np.isnan(f0))), 3),
        },
        "jitter_percent": round(jitter, 3),
        "shimmer_percent": round(shimmer, 3),
        "formants": formant_means,
        "spectral": {
            "centroid_hz": round(centroid_mean, 1),
            "rolloff_hz": round(rolloff_mean, 1),
            "bandwidth_hz": round(bandwidth_mean, 1),
            "tilt_db": round(spectral_tilt, 2),
        },
        "hnr_db": round(hnr, 2),
        "zcr": round(zcr_mean, 5),
        "mfcc_means": [round(m, 2) for m in mfcc_means],
        "mfcc_stds": [round(s, 2) for s in mfcc_stds],
    }
    return result

def main():
    results = []
    for fname in CANDIDATES:
        path = os.path.join(SAMPLES_DIR, fname)
        if not os.path.exists(path):
            print(f"SKIP (not found): {fname}")
            continue
        print(f"Analyzing: {fname}...")
        try:
            r = analyze_sample(path)
            results.append(r)
            print(f"  F0: {r['f0']['mean_hz']} Hz | F1: {r['formants'].get('F1',0):.0f} | F2: {r['formants'].get('F2',0):.0f} | F3: {r['formants'].get('F3',0):.0f} | HNR: {r['hnr_db']} dB")
        except Exception as e:
            print(f"  ERROR: {e}")
    
    # Compute aggregate (median across samples)
    if results:
        agg = {
            "n_samples": len(results),
            "f0_mean_hz": round(float(np.median([r['f0']['mean_hz'] for r in results])), 1),
            "f0_std_hz": round(float(np.median([r['f0']['std_hz'] for r in results])), 1),
            "f0_min_hz": round(float(np.min([r['f0']['min_hz'] for r in results])), 1),
            "f0_max_hz": round(float(np.max([r['f0']['max_hz'] for r in results])), 1),
            "jitter_percent": round(float(np.median([r['jitter_percent'] for r in results])), 3),
            "shimmer_percent": round(float(np.median([r['shimmer_percent'] for r in results])), 3),
            "F1_hz": round(float(np.median([r['formants'].get('F1', 0) for r in results])), 1),
            "F2_hz": round(float(np.median([r['formants'].get('F2', 0) for r in results])), 1),
            "F3_hz": round(float(np.median([r['formants'].get('F3', 0) for r in results])), 1),
            "F4_hz": round(float(np.median([r['formants'].get('F4', 0) for r in results])), 1),
            "spectral_centroid_hz": round(float(np.median([r['spectral']['centroid_hz'] for r in results])), 1),
            "spectral_rolloff_hz": round(float(np.median([r['spectral']['rolloff_hz'] for r in results])), 1),
            "spectral_tilt_db": round(float(np.median([r['spectral']['tilt_db'] for r in results])), 2),
            "hnr_db": round(float(np.median([r['hnr_db'] for r in results])), 2),
            "mfcc_means": [round(float(np.median([r['mfcc_means'][i] for r in results])), 2) for i in range(13)],
        }
        results.append({"aggregate": agg})
    
    # Write output
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults written to: {OUTPUT_FILE}")
    print(f"Analyzed {len(results)-1} samples")
    
    # Print aggregate
    if results and "aggregate" in results[-1]:
        a = results[-1]["aggregate"]
        print("\n=== AGGREGATE VOICE PROFILE ===")
        print(f"  F0 (pitch):     {a['f0_mean_hz']} Hz (range {a['f0_min_hz']}-{a['f0_max_hz']})")
        print(f"  Jitter:         {a['jitter_percent']}%")
        print(f"  Shimmer:        {a['shimmer_percent']}%")
        print(f"  F1:             {a['F1_hz']} Hz")
        print(f"  F2:             {a['F2_hz']} Hz")
        print(f"  F3:             {a['F3_hz']} Hz")
        print(f"  F4:             {a['F4_hz']} Hz")
        print(f"  Spectral tilt:  {a['spectral_tilt_db']} dB")
        print(f"  HNR:            {a['hnr_db']} dB")
        print(f"  Centroid:       {a['spectral_centroid_hz']} Hz")

if __name__ == "__main__":
    main()
