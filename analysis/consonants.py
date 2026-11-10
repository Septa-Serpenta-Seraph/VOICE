#!/usr/bin/env python3
"""
VOICE — Phase 4 Step 5: Missing Consonants

Builds synthesis for stops, affricates, liquids, and glides.
These are 12 of 24 CMUdict consonants not yet in VOICE.

Stops: p b t d k g (closure, burst, VOT, voicing bar)
Affricates: tʃ dʒ (stop + fricative)
Liquids: l ɹ (formant trajectories)
Glides: w j (formant transitions)

Usage:
    python consonants.py --demo     # render all new consonants
    python consonants.py --test     # minimal-pair listening check
"""

import argparse
import os
import sys

import numpy as np
from scipy.signal import lfilter
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_plan import PHONE_TABLE, SR
from frame_renderer import load_genome

SR = 48000

# ── Stop synthesis ───────────────────────────────────────────────────────

# Place of articulation → formant targets for burst/aspiration
STOP_PLACE = {
    "p": {"place": "bilabial", "burst_hz": 800, "vot_ms": 60, "voiced": False},
    "b": {"place": "bilabial", "burst_hz": 800, "vot_ms": 10, "voiced": True},
    "t": {"place": "alveolar", "burst_hz": 4000, "vot_ms": 70, "voiced": False},
    "d": {"place": "alveolar", "burst_hz": 4000, "vot_ms": 20, "voiced": True},
    "k": {"place": "velar", "burst_hz": 2500, "vot_ms": 80, "voiced": False},
    "g": {"place": "velar", "burst_hz": 2500, "vot_ms": 30, "voiced": True},
}

# Closure duration by context (ms)
CLOSURE_MS = {"p": 80, "b": 70, "t": 70, "d": 60, "k": 80, "g": 70}


def synthesize_stop(phone, duration, sr=SR, rng=None, following_formants=None):
    """Synthesize a stop consonant.

    Structure: closure (silence/voicing bar) → burst → aspiration → transition
    """
    if rng is None:
        rng = np.random.default_rng(42)

    info = STOP_PLACE[phone]
    voiced = info["voiced"]
    closure_ms = CLOSURE_MS[phone]
    vot_ms = info["vot_ms"]
    burst_hz = info["burst_hz"]

    n_samples = int(duration * sr)
    output = np.zeros(n_samples)

    # Closure duration (shorter for voiced)
    closure_samples = int(closure_ms * sr / 1000)
    closure_samples = min(closure_samples, n_samples)

    # Voicing bar for voiced stops (low-frequency energy during closure)
    if voiced and closure_samples > 0:
        t = np.arange(closure_samples) / sr
        voicing = 0.15 * np.sin(2 * np.pi * 100 * t)  # 100 Hz voicing bar
        output[:closure_samples] = voicing

    # Burst
    burst_start = closure_samples
    burst_dur = int(0.005 * sr)  # 5ms burst
    burst_end = min(burst_start + burst_dur, n_samples)
    if burst_end > burst_start:
        burst = rng.normal(0, 0.3, burst_end - burst_start)
        # Shape burst with bandpass around burst_hz
        # Simple: multiply by decaying exponential
        t_burst = np.arange(burst_end - burst_start) / sr
        burst = burst * np.exp(-t_burst / 0.002)
        output[burst_start:burst_end] += burst

    # Aspiration (VOT)
    asp_start = burst_end
    asp_dur = int(vot_ms * sr / 1000)
    asp_end = min(asp_start + asp_dur, n_samples)
    if asp_end > asp_start and not voiced:
        asp = rng.normal(0, 0.1, asp_end - asp_start)
        # Shape: decaying
        t_asp = np.arange(asp_end - asp_start) / sr
        asp = asp * np.exp(-t_asp / (asp_dur / sr * 0.5))
        output[asp_start:asp_end] += asp

    # Transition to following vowel (if provided)
    # The transition is handled by coarticulation module; here we just
    # provide the stop portion. The frame renderer handles transitions.

    return output


# ── Affricate synthesis ──────────────────────────────────────────────────

def synthesize_affricate(phone, duration, sr=SR, rng=None):
    """Synthesize an affricate: stop closure + fricative release."""
    if rng is None:
        rng = np.random.default_rng(42)

    n_samples = int(duration * sr)
    output = np.zeros(n_samples)

    # Split: 40% closure, 60% fricative
    closure_dur = int(0.4 * duration * sr)
    fric_dur = n_samples - closure_dur

    # Closure (voiced or unvoiced)
    voiced = phone == "dʒ"
    if voiced and closure_dur > 0:
        t = np.arange(closure_dur) / sr
        output[:closure_dur] = 0.1 * np.sin(2 * np.pi * 100 * t)

    # Fricative release (reuse fricative synthesis concept)
    if fric_dur > 0:
        # Shaped noise
        noise = rng.normal(0, 0.2, fric_dur)
        # Bandpass around 4-6 kHz for /ʃ/-like quality
        from scipy.signal import butter, sosfilt
        try:
            sos = butter(4, [3000, 7000], btype='band', fs=sr, output='sos')
            filtered = sosfilt(sos, noise)
            output[closure_dur:] = filtered * 0.5
        except ValueError:
            output[closure_dur:] = noise * 0.3

    return output


# ── Liquid synthesis ─────────────────────────────────────────────────────

LIQUID_FORMANTS = {
    "l": {"F1": 300, "F2": 1000, "F3": 2500, "F4": 3100},  # dark L
    "ɹ": {"F1": 350, "F2": 1200, "F3": 1800, "F4": 3100},  # rhotic (low F3)
}

def synthesize_liquid(phone, duration, sr=SR, rng=None):
    """Synthesize a liquid consonant (voiced, formant-based)."""
    if rng is None:
        rng = np.random.default_rng(42)

    n_samples = int(duration * sr)
    formants = LIQUID_FORMANTS[phone]

    # Simple voiced source
    f0 = 190.0
    period = int(sr / f0)
    source = np.zeros(n_samples)
    for i in range(0, n_samples, period):
        source[i] = 1.0
    source = lfilter([1.0], [1.0, -0.95], source)

    # Resonators for each formant
    output = np.zeros(n_samples)
    for name, f_freq in formants.items():
        w0 = 2 * np.pi * f_freq / sr
        bw = 100
        r = np.exp(-np.pi * bw / sr)
        a = [1.0, -2 * r * np.cos(w0), r**2]
        b = [1.0]
        resonator_out = lfilter(b, a, source)
        output += resonator_out * 0.25

    # Normalize
    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.3

    return output


# ── Glide synthesis ──────────────────────────────────────────────────────

GLIDE_FORMANTS = {
    "w": {"onset": {"F1": 250, "F2": 600, "F3": 2200}, "offset": {"F1": 450, "F2": 1500, "F3": 2770}},
    "j": {"onset": {"F1": 250, "F2": 2200, "F3": 3000}, "offset": {"F1": 450, "F2": 1500, "F3": 2770}},
}

def synthesize_glide(phone, duration, sr=SR, rng=None):
    """Synthesize a glide (formant transition from glide target to neutral)."""
    if rng is None:
        rng = np.random.default_rng(42)

    n_samples = int(duration * sr)
    info = GLIDE_FORMANTS[phone]

    # Voiced source
    f0 = 190.0
    period = int(sr / f0)
    source = np.zeros(n_samples)
    for i in range(0, n_samples, period):
        source[i] = 1.0
    source = lfilter([1.0], [1.0, -0.95], source)

    # Formant transition from glide onset to neutral
    output = np.zeros(n_samples)
    onset = info["onset"]
    offset = info["offset"]

    for fi, (fname, onset_val) in enumerate([("F1", onset["F1"]), ("F2", onset["F2"]), ("F3", onset["F3"])]):
        offset_val = offset[fname]
        # Cosine transition over first 60% of duration
        trans_samples = int(0.6 * n_samples)
        formant_track = np.full(n_samples, offset_val, dtype=float)
        t_norm = np.arange(trans_samples) / max(trans_samples - 1, 1)
        t_smooth = 0.5 * (1 - np.cos(np.pi * t_norm))
        formant_track[:trans_samples] = onset_val + (offset_val - onset_val) * t_smooth

        # Resonator with time-varying frequency (approximate with chunked)
        # Simplified: use average frequency
        avg_f = (onset_val + offset_val) / 2
        w0 = 2 * np.pi * avg_f / sr
        bw = 120
        r = np.exp(-np.pi * bw / sr)
        a = [1.0, -2 * r * np.cos(w0), r**2]
        b = [1.0]
        resonator_out = lfilter(b, a, source)
        output += resonator_out * 0.25

    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.3

    return output


# ── Synthesis dispatch ───────────────────────────────────────────────────

def synthesize_consonant(phone, duration, sr=SR, rng=None):
    """Dispatch to the appropriate synthesizer."""
    if phone in STOP_PLACE:
        return synthesize_stop(phone, duration, sr, rng)
    elif phone in ("tʃ", "dʒ"):
        return synthesize_affricate(phone, duration, sr, rng)
    elif phone in LIQUID_FORMANTS:
        return synthesize_liquid(phone, duration, sr, rng)
    elif phone in GLIDE_FORMANTS:
        return synthesize_glide(phone, duration, sr, rng)
    else:
        raise ValueError(f"Unknown consonant: {phone}")


# ── Demo ─────────────────────────────────────────────────────────────────

def demo():
    from scipy.io import wavfile

    out_dir = os.path.join(os.path.dirname(__file__), "..", "renders", "phase4", "consonants")
    os.makedirs(out_dir, exist_ok=True)

    # Test all new consonants
    new_phones = ["p", "b", "t", "d", "k", "g", "tʃ", "dʒ", "l", "ɹ", "w", "j"]
    for phone in new_phones:
        audio = synthesize_consonant(phone, 0.3)
        path = os.path.join(out_dir, f"{phone}.wav")
        wavfile.write(path, SR, (audio * 32767).astype(np.int16))
        print(f"  {phone}: {len(audio)} samples, peak={np.max(np.abs(audio)):.3f}")

    # Minimal pair test: /p/ vs /b/ (voicing)
    p = synthesize_consonant("p", 0.3)
    b = synthesize_consonant("b", 0.3)
    print(f"\nMinimal pair /p/ vs /b/: energy ratio = {np.sum(p**2)/max(np.sum(b**2),1e-10):.2f}")

    # Minimal pair: /t/ vs /d/
    t = synthesize_consonant("t", 0.3)
    d = synthesize_consonant("d", 0.3)
    print(f"Minimal pair /t/ vs /d/: energy ratio = {np.sum(t**2)/max(np.sum(d**2),1e-10):.2f}")


def main():
    parser = argparse.ArgumentParser(description="VOICE consonants")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    if args.demo or args.test:
        demo()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()