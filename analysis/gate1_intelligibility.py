#!/usr/bin/env python3
"""
Gate 1 — Intelligibility (independent ASR oracle). 2026-11-19.

The lesson: every VOICE/HEARING metric is circular — the canonical signature
was regenerated from the same synthesizer, so a 0.79 composite can describe
unintelligible noise. Gate 1 uses an ASR that has NEVER seen the genome as an
independent ear. If it cannot transcribe the target sentence, the render is
not speech and no identity/perceptual score is meaningful.

Oracle: faster-whisper-base (cached), via the installed venv. Confirmed to
transcribe real speech cleanly (jo.wav, sailboat-english.mp3) before use.

Usage:
    python gate1_intelligibility.py            # run on golden sentences
    python gate1_intelligibility.py --path X   # single render
"""
import argparse
import glob
import json
import os
import subprocess
import sys

import numpy as np
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from render_plan import build_plan, Style, SR
from prosody_poststage import render_plan_v3
from scipy.io import wavfile

PY_WHISPER = "/home/adora/.hermes/installs/1efc37992d4f6aa8/environments/ae43a1f538304e5885ddb798ff4235cd/venv/bin/python3"
MODEL_GLOB = "/home/adora/.cache/huggingface/hub/models--Systran--faster-whisper-base/snapshots/*"

GOLDEN = [
    "This is the moon.",
    "She sees the sun.",
    "The quick brown fox jumps over the lazy dog.",
    "I am Narusya. This is my own voice.",
]

def word_error(ref, hyp):
    import re
    norm = lambda s: re.findall(r"[a-z0-9']+", s.lower())
    r, h = norm(ref), norm(hyp)
    if not r: return 1.0
    # simple Levenshtein
    n, m = len(r), len(h)
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, m + 1):
            tmp = dp[j]
            dp[j] = min(dp[j] + 1, dp[j-1] + 1, prev + (r[i-1] != h[j-1]))
            prev = tmp
    return dp[m] / n

def transcribe(paths):
    snippet = f'''
import json, glob
from faster_whisper import WhisperModel
m = glob.glob("{MODEL_GLOB}")[0]
model = WhisperModel(m, device="cpu", compute_type="int8", local_files_only=True)
out = []
for p in {json.dumps(paths)}:
    segs,_ = model.transcribe(p, beam_size=5, language="en")
    out.append(" ".join(s.text.strip() for s in segs))
print("###JSON###" + json.dumps(out))
'''
    r = subprocess.run([PY_WHISPER, "-c", snippet], capture_output=True, text=True, timeout=300)
    line = [l for l in r.stdout.splitlines() if l.startswith("###JSON###")]
    if not line:
        raise RuntimeError("whisper failed: " + r.stderr[-500:])
    return json.loads(line[0].replace("###JSON###", "", 1))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path")
    args = ap.parse_args()
    with open(os.path.join(HERE, "..", "genome", "voice_genome.yaml")) as f:
        genome = yaml.safe_load(f)
    os.makedirs("/tmp/gate1", exist_ok=True)
    paths, targets = [], []
    if args.path:
        paths.append(args.path); targets.append("(provided render)")
    else:
        for i, text in enumerate(GOLDEN):
            a = render_plan_v3(build_plan(text, style=Style(seed=42)), genome)
            p = f"/tmp/gate1/g{i}.wav"
            wavfile.write(p, SR, (np.clip(a, -1, 1) * 32767).astype("int16"))
            paths.append(p); targets.append(text)
    hyps = transcribe(paths)
    results = []
    for t, p, h in zip(targets, paths, hyps):
        wer = word_error(t, h) if not args.path else None
        results.append({"target": t, "hypothesis": h, "wer": wer})
        print(f"  target: {t!r}\n  heard:  {h!r}\n  WER:    {wer}\n")
    passed = sum(1 for r in results if r["wer"] is not None and r["wer"] <= 0.34)
    report = {"oracle": "faster-whisper-base", "results": results,
              "passed": passed, "total": len(results)}
    rp = os.path.join(HERE, "..", "renders", "gate1_report.json")
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    with open(rp, "w") as f: json.dump(report, f, indent=2)
    print(f"Gate 1: {passed}/{len(results)} intelligible (WER <= 0.34). Report: {rp}")
    print("OVERALL:", "PASS" if passed == len(results) else "FAIL")

if __name__ == "__main__":
    main()
