#!/usr/bin/env python3
"""
VOICE — Gate 2 (speech): descriptor match on rendered sentences.

Gate 2 was originally run on sustained vowels (Phase 3, all_on_render.py).
This is the same gate against *speech* — the golden sentences through the
full Phase 4 pipeline — because the descriptor targets only mean something
on the audio that will actually be heard.

Measures, per sentence:
  tilt       PSD slope 100-4000 Hz, via HEARING's measure_render (authority)
  f0         mean F0 (Hz)
  hnr        harmonics-to-noise (dB)
  f0_anchor  |realized F0 - plan anchor| / anchor, at each anchor time
  sub_bass   PSD at F0/2 relative to PSD at F0 (dB), plus a unit-level
             assertion that the carrier sits at the genome's -18 dB

Thresholds (genome + Round 12 rulings):
  tilt      -1.30 +/- 0.30 dB/oct, judged on the sentence median
  f0        190.0 +/- 3 Hz
  hnr       reported only — Round 12: needs an independent target first
  anchor    median |err| < 5%
  sub_bass  carrier peak ratio -18 +/- 3 dB

This is an instrument, not a regression test: it reports pass/fail against
those thresholds so the open Gate 2 questions are answered with numbers
rather than impressions.

Usage:
    python gate2_speech.py          # table + report
    python gate2_speech.py --quiet  # report only
"""

import argparse
import json
import os
import sys
import tempfile

import numpy as np
from scipy.io import wavfile
from scipy.signal import welch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/adora/narusya-hearing/analysis")

from render_plan import build_plan, SR
from frame_renderer import load_genome
from prosody_poststage import (render_plan_v3, pitch_locked_sub_bass,
                               SUB_BASS_LEVEL_DB)
from time_varying import build_f0_track
from golden_set import GOLDEN_SENTENCES

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO, "renders", "gate2_speech")
REPORT = os.path.join(REPO, "renders", "gate2_speech_report.json")

TILT_TARGET = -1.30
TILT_TOL = 0.30
F0_TARGET = 190.0
F0_TOL = 3.0
ANCHOR_TOL_PCT = 5.0
SUB_LEVEL_TARGET = -37.0
SUB_LEVEL_TOL = 3.0
F0_CAPTURE_TOL_HZ = 2.0   # rendered F0 must stay this close to no-sub baseline


def slug(text):
    return (text.replace(" ", "_").replace(".", "").replace("!", "")
            .replace("?", "").replace(",", "").lower())


def measure(path):
    """HEARING's instrument: tilt / f0 / hnr."""
    from autonomous_eval import measure_render
    return measure_render(path)


def anchor_errors(plan):
    """|realized - anchor| / anchor at each anchor time, in percent."""
    if not plan.f0_anchors:
        return []
    n = int(plan.segments[-1].t1 * SR) + 240
    track = build_f0_track(plan, n)
    errs = []
    for a in plan.f0_anchors:
        i = max(0, min(n - 1, int(a.t * SR)))
        errs.append(100.0 * (track[i] - a.value) / a.value)
    return errs


def sub_bass_levels(plan, audio):
    """Spectral sub/fund ratio, plus the carrier's own peak level."""
    n = int(plan.segments[-1].t1 * SR) + 240
    f0_track = build_f0_track(plan, n)
    f0 = 190.0 * (1.0 + 0.03 * plan.style.effort)

    # Unit-level: carrier peak relative to a unit main signal.
    sub = pitch_locked_sub_bass(f0_track, SR, reference_peak=1.0)
    carrier_db = 20.0 * np.log10(np.max(np.abs(sub)))

    # Spectral: PSD at F0/2 vs PSD at F0, from the rendered audio.
    freqs, psd = welch(audio, fs=SR, nperseg=min(8192, len(audio)))

    def band(lo, hi):
        m = (freqs >= lo) & (freqs <= hi)
        return float(np.mean(psd[m])) if m.any() else 0.0

    spec_db = 10.0 * np.log10(band(f0 / 2 - 12, f0 / 2 + 12) /
                              band(f0 - 20, f0 + 20) + 1e-20)
    return carrier_db, spec_db


def f0_capture_deviation(plan, audio):
    """|F0 of rendered audio - F0 with sub disabled|, in Hz.

    The naming rule's real guardrail: the subharmonic must not capture the
    perceived pitch. A loud sub makes Praat lock onto F0/2, which reads as
    an octave drop. Compare against the same sentence with the sub off.
    """
    from autonomous_eval import measure_render
    import functools
    pp = __import__("prosody_poststage")
    orig = pp.pitch_locked_sub_bass

    def f0_of(samples):
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        wavfile.write(path, SR, (samples * 32767).astype(np.int16))
        try:
            m = measure_render(path)
        finally:
            os.unlink(path)
        return float(m.get("f0") or m.get("f0_hz") or 0.0)

    with_sub = f0_of(audio)
    pp.pitch_locked_sub_bass = functools.partial(orig, level_db=-120)
    try:
        base_audio = render_plan_v3(plan, load_genome(
            os.path.join(REPO, "genome", "voice_genome.yaml")))
        no_sub = f0_of(base_audio)
    finally:
        pp.pitch_locked_sub_bass = orig
    return with_sub - no_sub, with_sub, no_sub


def run(quiet=False):
    genome = load_genome(os.path.join(REPO, "genome", "voice_genome.yaml"))
    os.makedirs(OUT_DIR, exist_ok=True)

    rows = []
    for text in GOLDEN_SENTENCES:
        plan = build_plan(text)
        audio = render_plan_v3(plan, genome)
        path = os.path.join(OUT_DIR, slug(text) + ".wav")
        wavfile.write(path, SR, (audio * 32767).astype(np.int16))

        m = measure(path)
        errs = anchor_errors(plan)
        carrier_db, spec_db = sub_bass_levels(plan, audio)
        cap_dev, f0_with, f0_base = f0_capture_deviation(plan, audio)

        rows.append({
            "text": text,
            "tilt_db_oct": round(float(m.get("tilt", 0.0)), 3),
            "f0_hz": round(float(m.get("f0", 0.0)), 2),
            "hnr_db": round(float(m.get("hnr", 0.0)), 2),
            "anchor_err_pct": [round(e, 2) for e in errs],
            "anchor_err_median_pct": round(float(np.median(np.abs(errs))), 2) if errs else None,
            "sub_carrier_db": round(carrier_db, 2),
            "sub_fund_db": round(spec_db, 2),
            "f0_capture_dev_hz": round(float(cap_dev), 2),
            "f0_no_sub_hz": round(float(f0_base), 2),
        })

    tilts = [r["tilt_db_oct"] for r in rows]
    f0s = [r["f0_hz"] for r in rows]
    med_tilt = float(np.median(tilts))
    med_f0 = float(np.median(f0s))
    anchor_medians = [r["anchor_err_median_pct"] for r in rows
                      if r["anchor_err_median_pct"] is not None]
    med_anchor = float(np.median(anchor_medians)) if anchor_medians else None
    carriers = [r["sub_carrier_db"] for r in rows]
    med_carrier = float(np.median(carriers))
    cap_devs = [abs(r["f0_capture_dev_hz"]) for r in rows]
    worst_capture = float(max(cap_devs)) if cap_devs else None

    checks = {
        "tilt_median": {
            "value": round(med_tilt, 3), "target": TILT_TARGET,
            "tol": TILT_TOL,
            "pass": abs(med_tilt - TILT_TARGET) <= TILT_TOL,
        },
        "f0_median": {
            "value": round(med_f0, 2), "target": F0_TARGET,
            "tol": F0_TOL,
            "pass": abs(med_f0 - F0_TARGET) <= F0_TOL,
        },
        "f0_anchor_tracking": {
            "value": round(med_anchor, 2) if med_anchor is not None else None,
            "target_max_pct": ANCHOR_TOL_PCT,
            "pass": (med_anchor is not None and med_anchor <= ANCHOR_TOL_PCT),
        },
        "sub_bass_carrier": {
            "value": round(med_carrier, 2), "target": SUB_LEVEL_TARGET,
            "tol": SUB_LEVEL_TOL,
            "pass": abs(med_carrier - SUB_LEVEL_TARGET) <= SUB_LEVEL_TOL,
        },
        "f0_not_captured": {
            "value": round(worst_capture, 2) if worst_capture is not None else None,
            "target_max_hz": F0_CAPTURE_TOL_HZ,
            "pass": (worst_capture is not None and worst_capture <= F0_CAPTURE_TOL_HZ),
        },
    }
    overall = all(c["pass"] for c in checks.values())

    report = {
        "gate": "Gate 2 — descriptor match on speech",
        "instrument": "HEARING measure_render (tilt 100-4000 Hz, true dB/oct)",
        "n_sentences": len(rows),
        "checks": checks,
        "overall": overall,
        "sentences": rows,
    }
    with open(REPORT, "w") as f:
        json.dump(report, f, indent=2)

    if not quiet:
        print("=" * 78)
        print("GATE 2 — DESCRIPTOR MATCH ON SPEECH")
        print("=" * 78)
        print(f"{'sentence':42s} {'tilt':>7s} {'f0':>7s} {'hnr':>7s} "
              f"{'anch%':>7s} {'subdB':>7s}")
        for r in rows:
            am = r["anchor_err_median_pct"]
            print(f"{r['text'][:40]:42s} {r['tilt_db_oct']:7.2f} "
                  f"{r['f0_hz']:7.1f} {r['hnr_db']:7.2f} "
                  f"{(am if am is not None else float('nan')):7.2f} "
                  f"{r['sub_carrier_db']:7.2f}")
        print()
        for name, c in checks.items():
            mark = "PASS" if c["pass"] else "FAIL"
            print(f"  [{mark}] {name}: {c}")
        print(f"\n  overall: {'PASS' if overall else 'FAIL'}")
        print(f"  report: {REPORT}")
    return report


def main():
    ap = argparse.ArgumentParser(description="Gate 2 on speech renders")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    run(quiet=args.quiet)


if __name__ == "__main__":
    main()
