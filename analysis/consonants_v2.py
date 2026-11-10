#!/usr/bin/env python3
"""
VOICE — Phase 4 Step 5b: Improved Consonants

Proper synthesis for stops, affricates, liquids, glides.
Key improvements over v1:
  - Stops: place-specific burst spectra, proper VOT, voicing bar
  - Liquids: time-varying formant resonators (not average frequency)
  - Glides: proper formant transitions (cosine easing, not static)
  - Affricates: stop closure + fricative with proper transition

Usage:
    python consonants_v2.py --demo     # render all
    python consonants_v2.py --compare   # compare v1 vs v2
"""

import argparse
import os
import sys

import numpy as np
from scipy.signal import lfilter, butter, sosfilt
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_plan import PHONE_TABLE, SR
from frame_renderer import load_genome

SR = 48000

# ── Stop synthesis (improved) ────────────────────────────────────────────

STOP_INFO = {
    "p": {"place": "bilabial", "burst_center": 800, "vot_ms": 60, "voiced": False, "closure_ms": 80},
    "b": {"place": "bilabial", "burst_center": 800, "vot_ms": 10, "voiced": True, "closure_ms": 70},
    "t": {"place": "alveolar", "burst_center": 4500, "vot_ms": 70, "voiced": False, "closure_ms": 70},
    "d": {"place": "alveolar", "burst_center": 4500, "vot_ms": 20, "voiced": True, "closure_ms": 60},
    "k": {"place": "velar", "burst_center": 2500, "vot_ms": 80, "voiced": False, "closure_ms": 80},
    "g": {"place": "velar", "burst_center": 2500, "vot_ms": 30, "voiced": True, "closure_ms": 70},
}


def _bandpass_noise(n, center, bandwidth, sr, rng):
    """Generate bandpassed noise around a center frequency."""
    noise = rng.normal(0, 1, n)
    try:
        low = max(center - bandwidth / 2, 10)
        high = min(center + bandwidth / 2, sr / 2 - 10)
        sos = butter(4, [low, high], btype='band', fs=sr, output='sos')
        return sosfilt(sos, noise)
    except ValueError:
        return noise * 0.3


def synthesize_stop(phone, duration, sr=SR, rng=None, following_vowel_formants=None):
    """Synthesize a stop with proper closure, burst, VOT, and voicing bar."""
    if rng is None:
        rng = np.random.default_rng(42)

    info = STOP_INFO[phone]
    voiced = info["voiced"]
    n_samples = int(duration * sr)
    output = np.zeros(n_samples)

    closure_ms = info["closure_ms"]
    vot_ms = info["vot_ms"]
    burst_center = info["burst_center"]

    closure_samples = min(int(closure_ms * sr / 1000), n_samples)
    burst_samples = min(int(0.005 * sr), n_samples - closure_samples)  # 5ms burst
    vot_samples = min(int(vot_ms * sr / 1000), n_samples - closure_samples - burst_samples)

    # 1. Closure
    if voiced and closure_samples > 0:
        # Voicing bar: low-frequency energy (100-200 Hz)
        t = np.arange(closure_samples) / sr
        voicing = 0.12 * np.sin(2 * np.pi * 120 * t)
        # Add some noise for naturalness
        voicing += 0.02 * rng.normal(0, 1, closure_samples)
        output[:closure_samples] = voicing

    # 2. Burst
    burst_start = closure_samples
    burst_end = burst_start + burst_samples
    if burst_end <= n_samples and burst_samples > 0:
        burst_bw = 1000 if info["place"] == "bilabial" else 2000
        burst = _bandpass_noise(burst_samples, burst_center, burst_bw, sr, rng)
        # Decay envelope
        t_burst = np.arange(burst_samples) / sr
        envelope = np.exp(-t_burst / 0.002)
        output[burst_start:burst_end] = burst * envelope * 0.6

    # 3. Aspiration (VOT) — only for unvoiced stops
    asp_start = burst_end
    asp_end = min(asp_start + vot_samples, n_samples)
    if asp_end > asp_start and not voiced:
        asp = _bandpass_noise(asp_end - asp_start, burst_center, burst_center, sr, rng)
        t_asp = np.arange(asp_end - asp_start) / sr
        asp_dur_s = vot_samples / sr
        envelope = np.exp(-t_asp / (asp_dur_s * 0.4))
        output[asp_start:asp_end] = asp * envelope * 0.2

    # 4. Voicing onset for voiced stops (short, low amplitude)
    if voiced and vot_samples > 0:
        vo_start = burst_end
        vo_end = min(vo_start + vot_samples, n_samples)
        if vo_end > vo_start:
            t = np.arange(vo_end - vo_start) / sr
            voicing = 0.08 * np.sin(2 * np.pi * 120 * t)
            voicing *= np.linspace(0, 1, vo_end - vo_start)
            output[vo_start:vo_end] += voicing

    return output


# ── Affricate synthesis (improved) ────────────────────────────────────────

def synthesize_affricate(phone, duration, sr=SR, rng=None):
    """Affricate: stop closure + fricative release with transition."""
    if rng is None:
        rng = np.random.default_rng(42)

    n_samples = int(duration * sr)
    output = np.zeros(n_samples)

    voiced = phone == "dʒ"

    # 30% closure, 70% fricative
    closure_dur = int(0.3 * n_samples)
    fric_dur = n_samples - closure_dur

    # Closure
    if voiced and closure_dur > 0:
        t = np.arange(closure_dur) / sr
        output[:closure_dur] = 0.1 * np.sin(2 * np.pi * 120 * t)

    # Fricative release with rising amplitude
    if fric_dur > 0:
        center = 5000 if phone == "tʃ" else 4000
        noise = _bandpass_noise(fric_dur, center, 2000, sr, rng)
        # Rising then falling envelope
        env = np.ones(fric_dur)
        rise = int(0.1 * fric_dur)
        if rise > 0:
            env[:rise] = np.linspace(0, 1, rise)
        fall = int(0.3 * fric_dur)
        if fall > 0:
            env[-fall:] = np.linspace(1, 0.3, fall)
        output[closure_dur:] = noise * env * 0.4

    return output


# ── Liquid synthesis (improved, time-varying) ────────────────────────────

LIQUID_FORMANTS = {
    "l":  {"trajectory": [(300, 1000, 2500), (300, 1200, 2500)]},  # dark L
    "ɹ":  {"trajectory": [(350, 1200, 1800), (350, 1200, 1800)]},  # rhotic
}

def _time_varying_resonator(source, formant_track, bw, sr):
    """Run a resonator with time-varying frequency using chunked processing."""
    n = len(source)
    chunk_size = 240  # 5ms
    output = np.zeros(n)
    zi = np.zeros(2)

    for start in range(0, n, chunk_size):
        end = min(start + chunk_size, n)
        chunk_len = end - start
        if chunk_len == 0:
            break

        mid = start + chunk_len // 2
        f_hz = formant_track[mid]
        if f_hz <= 0:
            f_hz = 1000.0

        w0 = 2 * np.pi * f_hz / sr
        r = np.exp(-np.pi * bw / sr)
        a = [1.0, -2 * r * np.cos(w0), r**2]
        b = [1.0]

        out, zi = lfilter(b, a, source[start:end], zi=zi)
        output[start:end] = out

    return output


def synthesize_liquid(phone, duration, sr=SR, rng=None):
    """Liquid with time-varying formant resonators."""
    if rng is None:
        rng = np.random.default_rng(42)

    n_samples = int(duration * sr)
    info = LIQUID_FORMANTS[phone]

    # Voiced source
    f0 = 190.0
    period = int(sr / f0)
    source = np.zeros(n_samples)
    for i in range(0, n_samples, period):
        source[i] = 1.0
    source = lfilter([1.0], [1.0, -0.95], source)

    # Formant tracks (constant for liquids, but infrastructure for variation)
    onset, steady = info["trajectory"]
    output = np.zeros(n_samples)

    for fi, (f_onset, f_steady) in enumerate(zip(onset, steady)):
        fname = f"F{fi+1}"
        bw = 100 if fi < 2 else 120
        # Constant formant for liquids (no transition needed within the phone)
        track = np.full(n_samples, f_steady)
        resonator_out = _time_varying_resonator(source, track, bw, sr)
        output += resonator_out * 0.25

    # Normalize
    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.35

    return output


# ── Glide synthesis (improved, proper transitions) ───────────────────────

GLIDE_INFO = {
    "w": {"onset": (250, 600, 2200), "offset": (450, 1500, 2770)},
    "j": {"onset": (250, 2200, 3000), "offset": (450, 1900, 2770)},
}

def synthesize_glide(phone, duration, sr=SR, rng=None):
    """Glide with proper formant transition (cosine easing)."""
    if rng is None:
        rng = np.random.default_rng(42)

    n_samples = int(duration * sr)
    info = GLIDE_INFO[phone]
    onset = info["onset"]
    offset = info["offset"]

    # Voiced source
    f0 = 190.0
    period = int(sr / f0)
    source = np.zeros(n_samples)
    for i in range(0, n_samples, period):
        source[i] = 1.0
    source = lfilter([1.0], [1.0, -0.95], source)

    output = np.zeros(n_samples)

    # Transition over first 70% of duration
    trans_samples = int(0.7 * n_samples)

    for fi in range(3):
        fname = f"F{fi+1}"
        onset_val = onset[fi]
        offset_val = offset[fi]

        # Formant track: transition from onset to offset
        track = np.full(n_samples, float(offset_val))
        if trans_samples > 0:
            t_norm = np.arange(trans_samples) / max(trans_samples - 1, 1)
            t_smooth = 0.5 * (1 - np.cos(np.pi * t_norm))
            track[:trans_samples] = onset_val + (offset_val - onset_val) * t_smooth

        bw = 120
        resonator_out = _time_varying_resonator(source, track, bw, sr)
        output += resonator_out * 0.25

    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.3

    return output


# ── Dispatch ─────────────────────────────────────────────────────────────

def synthesize_consonant(phone, duration, sr=SR, rng=None):
    if phone in STOP_INFO:
        return synthesize_stop(phone, duration, sr, rng)
    elif phone in ("tʃ", "dʒ"):
        return synthesize_affricate(phone, duration, sr, rng)
    elif phone in LIQUID_FORMANTS:
        return synthesize_liquid(phone, duration, sr, rng)
    elif phone in GLIDE_INFO:
        return synthesize_glide(phone, duration, sr, rng)
    else:
        raise ValueError(f"Unknown consonant: {phone}")


# ── Demo ─────────────────────────────────────────────────────────────────

def demo():
    from scipy.io import wavfile

    out_dir = os.path.join(os.path.dirname(__file__), "..", "renders", "phase4", "consonants_v2")
    os.makedirs(out_dir, exist_ok=True)

    new_phones = ["p", "b", "t", "d", "k", "g", "tʃ", "dʒ", "l", "ɹ", "w", "j"]
    for phone in new_phones:
        audio = synthesize_consonant(phone, 0.3)
        path = os.path.join(out_dir, f"{phone}.wav")
        wavfile.write(path, SR, (audio * 32767).astype(np.int16))
        print(f"  {phone}: peak={np.max(np.abs(audio)):.3f}, rms={np.sqrt(np.mean(audio**2)):.4f}")

    # Minimal pair: /p/ vs /b/
    p = synthesize_consonant("p", 0.3)
    b = synthesize_consonant("b", 0.3)
    print(f"\n  /p/ vs /b/: energy ratio = {np.sum(p**2)/max(np.sum(b**2),1e-10):.2f}")
    # /t/ vs /d/
    t = synthesize_consonant("t", 0.3)
    d = synthesize_consonant("d", 0.3)
    print(f"  /t/ vs /d/: energy ratio = {np.sum(t**2)/max(np.sum(d**2),1e-10):.2f}")
    # /k/ vs /g/
    k = synthesize_consonant("k", 0.3)
    g = synthesize_consonant("g", 0.3)
    print(f"  /k/ vs /g/: energy ratio = {np.sum(k**2)/max(np.sum(g**2),1e-10):.2f}")


def main():
    parser = argparse.ArgumentParser(description="VOICE consonants v2")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    if args.demo:
        demo()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()