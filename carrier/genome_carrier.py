#!/usr/bin/env python3
"""Genome-conditioned neural carrier — first hybrid prototype (Round 23 / option a).

The formant-synth genome voice has identity but hit an intelligibility ceiling
(Round 22: 2/8 phonemes vs natural 6/8; every in-paradigm lever failed). This
carrier takes a DIFFERENT throat: an intelligible offline neural TTS (Piper
libritts-high) and conditions it toward the genome's identity spec.

First prototype conditioning = F0 alignment to the genome's running-speech
median (measured_f0_median_hz), formant-preserving so vowel identity and
intelligibility survive. Deeper timbre/formant/glottal conditioning is the next
investment; this is the honest first carrier, not the finished genome voice.

Sovereign: fully offline, no cloud. Carrier F0 is measured per utterance and the
pitch ratio is derived from the genome target, so code and genome cannot drift.

Usage:
  python genome_carrier.py "text to speak" --out /mnt/data/nar_carrier.mp3
  python genome_carrier.py "text" --out x.mp3 --raw   # unconditioned carrier
"""
import argparse
import os
import subprocess
import sys

import numpy as np
import soundfile as sf
import parselmouth
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
GENOME = os.path.normpath(os.path.join(HERE, "..", "genome", "voice_genome.yaml"))
PIPER = os.path.expanduser("~/.local/bin/piper")
PIPER_LIB = os.path.expanduser("~/.local/lib/piper")
DEFAULT_MODEL = "/mnt/data/piper-voices/en_US-libritts-high.onnx"
VENV_PY = "/mnt/data/pocket-tts-venv/bin/python"


def genome_f0_target():
    g = yaml.safe_load(open(GENOME))
    return float(g["prosody"]["measured_f0_median_hz"]) if "prosody" in g and \
        "measured_f0_median_hz" in g.get("prosody", {}) else _find_f0(g)


def _find_f0(g):
    # measured_f0_median_hz lives near the top level of the genome
    def walk(d):
        if isinstance(d, dict):
            if "measured_f0_median_hz" in d:
                return float(d["measured_f0_median_hz"])
            for v in d.values():
                r = walk(v)
                if r is not None:
                    return r
        return None
    return walk(g) or 190.9


def render_carrier(text, wav_path, model=DEFAULT_MODEL):
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = PIPER_LIB + ":" + env.get("LD_LIBRARY_PATH", "")
    env["ESPEAK_DATA_PATH"] = os.path.join(PIPER_LIB, "espeak-ng-data")
    p = subprocess.run([PIPER, "--model", model, "--output_file", wav_path],
                       input=text.encode(), env=env, capture_output=True)
    if p.returncode != 0 or not os.path.exists(wav_path):
        raise RuntimeError("piper failed: " + p.stderr.decode()[-400:])
    return wav_path


def f0_median(wav_path):
    y, sr = sf.read(wav_path)
    y = y.astype(np.float64)
    if y.ndim > 1:
        y = y.mean(1)
    snd = parselmouth.Sound(y, sr)
    pit = snd.to_pitch(time_step=0.01, pitch_floor=75, pitch_ceiling=500)
    v = pit.selected_array["frequency"]
    v = v[np.isfinite(v) & (v > 0)]
    return float(np.median(v)) if len(v) else 0.0


def condition(wav_path, out_mp3, target_hz, raw=False):
    base = f0_median(wav_path)
    if raw or base <= 0:
        ratio = 1.0
    else:
        ratio = target_hz / base
        # Robustness guard: an octave-error in the carrier F0 estimate must not
        # drive an extreme transposition. Clamp to a sane register band; the
        # deeper fix is octave-robust F0 estimation (next investment).
        ratio = max(0.80, min(1.25, ratio))
    # formant=preserved keeps vowel identity / intelligibility; only F0 moves.
    af = f"rubberband=pitch={ratio:.4f}:formant=preserved:pitchq=1.0,loudnorm=I=-16:TP=-2"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", wav_path, "-af", af, "-ar", "48000", out_mp3], check=True)
    return base, ratio


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--raw", action="store_true", help="skip genome conditioning")
    args = ap.parse_args()

    target = genome_f0_target()
    wav = os.path.splitext(args.out)[0] + "_carrier.wav"
    render_carrier(args.text, wav, args.model)
    base, ratio = condition(wav, args.out, target, raw=args.raw)
    print(f"genome F0 target {target:.1f} Hz | carrier F0 {base:.1f} Hz | "
          f"pitch ratio {ratio:.3f} | conditioned F0 ~{base*ratio:.1f} Hz | out {args.out}")


if __name__ == "__main__":
    main()
