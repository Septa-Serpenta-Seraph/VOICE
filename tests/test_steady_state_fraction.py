#!/usr/bin/env python3
"""Round 17 guard: every vowel keeps >= 40% steady state after transitions.

The Round 16 fix removed the 48x stretch but left a fixed ~110ms transition
tax (CV 60 + VC 50 written) on every vowel. At 142.5 wpm most vowels are
127-195ms, so short vowels were 86% glide. This guard asserts the proportional budget keeps >= 40% steady state on the golden set, and a
mutation test proves it FIRES on the legacy fixed budget (not a no-op).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "analysis"))
from render_plan import build_plan, Style
import time_varying as tv
import prosody_poststage as pp

GOLDEN = [
    "This is the moon.",
    "She sees the sun.",
    "The quick brown fox jumps over the lazy dog.",
    "I am Narusya. This is my own voice.",
]


def vowel_steady_fractions(prop):
    fracs = []
    for text in GOLDEN:
        pl = pp.plan_prosody_v2(build_plan(text, style=Style(seed=42)))
        segs = sorted([s for s in pl.segments if s.kind != "silence"],
                      key=lambda s: s.t0)
        for j, s in enumerate(segs):
            if s.kind not in ("vowel", "diphthong"):
                continue
            D = (s.t1 - s.t0) * 1000
            prev_c = j > 0 and segs[j-1].kind not in ("vowel", "diphthong")
            next_c = j < len(segs)-1 and segs[j+1].kind not in ("vowel", "diphthong")
            if prop:
                cv = tv.transition_written_ms(D, 60) if prev_c else 0
                vc = tv.transition_written_ms(D, 50) if next_c else 0
            else:
                cv = 60 if prev_c else 0
                vc = 50 if next_c else 0
            fracs.append((text, s.phone, D, (D - cv - vc) / D))
    return fracs


def test_steady_state_fraction():
    fracs = vowel_steady_fractions(prop=True)
    bad = [(t, p, round(D), round(f, 2)) for t, p, D, f in fracs if f < 0.40]
    assert not bad, f"vowels below 40% steady state: {bad[:6]}"


def test_guard_fires_on_legacy():
    fracs = vowel_steady_fractions(prop=False)
    bad = [(t, p, round(D), round(f, 2)) for t, p, D, f in fracs if f < 0.40]
    assert bad, "guard would not fire on the legacy fixed budget (no-op guard)"


if __name__ == "__main__":
    test_steady_state_fraction()
    print("OK  proportional budget: all golden vowels >= 40% steady state")
    try:
        test_guard_fires_on_legacy()
        print("OK  guard fires on legacy fixed 110ms tax")
    except AssertionError as e:
        print("!!! guard did NOT fire on legacy (bad):", e)
        sys.exit(1)
