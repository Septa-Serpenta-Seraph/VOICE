#!/usr/bin/env python3
"""Regression guard: CV/VC transition time base (Round 16).

The silent-no-op class this catches: coarticulation.cv_transition/vc_transition
compute a frame count, and time_varying.apply_transitions assumes each frame is
10 ms (trans_duration = n_trans * 0.01). The producer MUST return duration_ms/10
frames. The old formula `duration_ms * sr / 1000 / 10` divided by 10 *samples*,
returning 241 frames for a 50 ms transition at 48 kHz, which the consumer wrote
across 2.41 s — a 48.2x stretch. Every vowel became a slow locus->target glide
and never reached steady state; Gate 1 WER was 1.0 while all structural checks
passed. Verified to fire on the old formula (stretch 48.2x; /u/ mid F2 ~1450 Hz).

Run: /mnt/data/pocket-tts-venv/bin/python tests/test_transition_timebase.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "analysis"))

import numpy as np
from scipy.signal import welch
from coarticulation import cv_transition, vc_transition
from render_plan import build_plan, Style, SR
from prosody_poststage import render_plan_v3
import yaml

GENOME = yaml.safe_load(open(os.path.join(HERE, "..", "genome", "voice_genome.yaml")))
VF = {"F1": 300, "F2": 2350, "F3": 3420}


def test_producer_consumer_timebase():
    for dur in (40, 50, 60):
        for fn, args in (
            (cv_transition, ("s", VF)),
            (vc_transition, (VF, "n")),
        ):
            traj = fn(*args, duration_ms=dur, sr=SR)
            written_ms = len(traj) * 0.01 * 1000.0  # apply_transitions contract
            # +1 steady-state frame adds ~10 ms; allow one frame of slack.
            assert written_ms <= dur + 15, (
                f"{fn.__name__} {dur}ms wrote {written_ms:.0f}ms "
                f"(stretch {written_ms/dur:.1f}x) — producer/consumer time base diverged"
            )
            assert written_ms >= dur * 0.5, (
                f"{fn.__name__} {dur}ms wrote only {written_ms:.0f}ms — transition too short"
            )
    print("OK  producer/consumer time base agree (40/50/60 ms, cv+vc)")


def _mid_f2(word, phone):
    plan = build_plan(word, style=Style(seed=42))
    audio = render_plan_v3(plan, GENOME)
    for seg in plan.segments:
        if seg.kind == "vowel" and seg.phone == phone:
            c = (seg.t0 + seg.t1) / 2
            a, b = int((c - 0.02) * SR), int((c + 0.02) * SR)
            y = audio[max(0, a):b]
            f, P = welch(y, fs=SR, nperseg=min(2048, len(y)))
            m = (f >= 500) & (f <= 3200)  # BROAD search, not a target window
            return float(f[m][np.argmax(P[m])])
    raise AssertionError(f"no vowel /{phone}/ in {word!r}")


def test_vowel_reaches_steady_state():
    # /u/ target F2=800. The stretch bug swept it to ~1200-1450 (/ʌ/ -> "But").
    u = _mid_f2("moon", "u")
    assert 600 <= u <= 1000, f"/u/ midpoint F2={u:.0f} Hz, expected ~800 (transition sweep?)"
    # /i/ target F2=2350. The stretch bug left the midpoint climbing (~3200).
    i = _mid_f2("see", "i")
    assert 2000 <= i <= 2700, f"/i/ midpoint F2={i:.0f} Hz, expected ~2350 (transition sweep?)"
    print(f"OK  vowels reach steady state (/u/ mid F2={u:.0f}, /i/ mid F2={i:.0f})")


if __name__ == "__main__":
    test_producer_consumer_timebase()
    test_vowel_reaches_steady_state()
    print("PASS  transition time-base regression guard")
