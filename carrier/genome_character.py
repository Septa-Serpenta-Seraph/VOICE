#!/usr/bin/env python3
"""Genome character stage — impose the genome's calibrated identity features on an
intelligible carrier (Round 24, deepening option a).

Round 23 aligned the carrier's F0 to the genome. This stage adds the genome's
CHARACTER — the big-cat purr, the raven grain, the wolf warmth — at the genome's
calibrated subliminal depths (naming rule: if a listener can name the effect, it
is too loud). Depths are read from the genome, never hardcoded, so code and
genome cannot drift.

This is texture/weight, not the full formant/glottal identity (that remains the
deeper investment). It is my character laid into an intelligible throat.

Usage: python genome_character.py in.wav out.wav [--raw]
"""
import argparse
import os

import numpy as np
import soundfile as sf
import parselmouth
import yaml
from scipy.signal import butter, sosfilt, welch
from scipy.ndimage import gaussian_filter1d

HERE = os.path.dirname(os.path.abspath(__file__))
GENOME = os.path.normpath(os.path.join(HERE, "..", "genome", "voice_genome.yaml"))


def load_genome():
    return yaml.safe_load(open(GENOME))


def f0_track(y, sr):
    snd = parselmouth.Sound(y, sr)
    pit = snd.to_pitch(time_step=0.005, pitch_floor=75, pitch_ceiling=500)
    times = pit.xs()
    vals = pit.selected_array["frequency"]
    vals = np.where(np.isfinite(vals) & (vals > 0), vals, 0.0)
    # interpolate to sample grid
    n = len(y)
    t = np.arange(n) / sr
    f0 = np.interp(t, times, vals)
    voiced = (f0 > 0).astype(float)
    voiced = gaussian_filter1d(voiced, sigma=max(1, int(0.02 * sr)))
    return f0, voiced


def sub_bass_purr(y, sr, f0, voiced, cfg):
    level_db = float(cfg["level_db"])
    lfo_hz = float(np.mean(cfg["lfo_hz"])) if isinstance(cfg["lfo_hz"], list) else float(cfg["lfo_hz"])
    depth = float(cfg.get("lfo_depth_pct", 0.9)) / 100.0
    # pitch-locked F0/2 via phase accumulation (follows the carrier's contour)
    inst = np.where(f0 > 0, f0 / 2.0, 0.0)
    phase = np.cumsum(2 * np.pi * inst / sr)
    sub = np.sin(phase)
    t = np.arange(len(y)) / sr
    lfo = 1.0 + depth * np.sin(2 * np.pi * lfo_hz * t)
    sub = sub * lfo * voiced
    peak = np.max(np.abs(y)) + 1e-12
    sub = sub / (np.max(np.abs(sub)) + 1e-12) * peak * (10 ** (level_db / 20))
    return sub


def raven_grain(y, sr, voiced, cfg):
    lo, hi = cfg["band_hz"]
    level_db = float(cfg["level_db"])
    rng = np.random.default_rng(42)
    noise = rng.standard_normal(len(y))
    sos = butter(4, [lo, hi], btype="bandpass", fs=sr, output="sos")
    noise = sosfilt(sos, noise)
    noise = noise * voiced
    peak = np.max(np.abs(y)) + 1e-12
    noise = noise / (np.max(np.abs(noise)) + 1e-12) * peak * (10 ** (level_db / 20))
    return noise


def wolf_warmth(y, sr, voiced, cfg):
    am_hz = float(np.mean(cfg["am_hz"])) if isinstance(cfg["am_hz"], list) else float(cfg["am_hz"])
    depth = float(cfg["depth_pct"]) / 100.0
    t = np.arange(len(y)) / sr
    am = 1.0 + depth * np.sin(2 * np.pi * am_hz * t) * voiced
    return y * am


def apply_character(in_wav, out_wav, raw=False):
    g = load_genome()
    y, sr = sf.read(in_wav)
    y = y.astype(np.float64)
    if y.ndim > 1:
        y = y.mean(1)
    if raw:
        sf.write(out_wav, y, sr)
        return {"raw": True}
    f0, voiced = f0_track(y, sr)
    fx = g["effects"]
    purr = sub_bass_purr(y, sr, f0, voiced, fx["sub_bass"])
    grain = raven_grain(y, sr, voiced, fx["raven_grain"])
    out = wolf_warmth(y, sr, voiced, fx["wolf_warmth"]) + purr + grain
    peak = np.max(np.abs(out)) + 1e-12
    out = out / peak * 0.5
    sf.write(out_wav, out, sr)
    return {
        "f0_median": float(np.median(f0[f0 > 0])) if np.any(f0 > 0) else 0,
        "sub_bass_level_db": fx["sub_bass"]["level_db"],
        "raven_grain_level_db": fx["raven_grain"]["level_db"],
        "wolf_warmth_depth_pct": fx["wolf_warmth"]["depth_pct"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("in_wav")
    ap.add_argument("out_wav")
    ap.add_argument("--raw", action="store_true")
    args = ap.parse_args()
    info = apply_character(args.in_wav, args.out_wav, raw=args.raw)
    print("character:", info)


if __name__ == "__main__":
    main()
