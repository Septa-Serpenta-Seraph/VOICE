#!/usr/bin/env python3
"""
VOICE — Gate 2 (speech): descriptor match on rendered sentences.

Gate 2 was originally run on sustained vowels (Phase 3, all_on_render.py).
This is the same gate against *speech* — the golden sentences through the
full Phase 4 pipeline — because the descriptor targets only mean something
on the audio that will actually be heard.

Measures, per sentence:
  tilt       PSD slope 100-4000 Hz, via HEARING's measure_render (authority,
             informational on speech — see genome changelog 0.3.11)
  f0         true median of voiced frames (f0_median), plus mean (f0, legacy)
  hnr        harmonics-to-noise (dB)
  fidelity   |F0 in AUDIO - plan track| % at anchors AND voiced-frame quartiles
  sub_bass   PSD at F0/2 relative to PSD at F0 (dB), plus a unit-level
             assertion that the carrier sits at the genome's level_db

Thresholds (genome + Round 12/13/14 rulings):
  tilt      -1.30 +/- 0.30 dB/oct, INFORMATIONAL on speech, not a gate
  f0        genome measured_f0_median_hz (190.9) +/- 3, on the true median
  hnr       reported only — needs an independent target first
  fidelity  median audio-vs-track err < 5%
  sub_bass  carrier peak ratio from genome effects.sub_bass.level_db +/- 3 dB

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
# HEARING path: allow override via env, fall back to sibling checkout.
_HEARING = os.environ.get("NARUSYA_HEARING_ANALYSIS", os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "narusya-hearing", "analysis")))
sys.path.insert(0, _HEARING)

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
F0_TARGET = 190.9   # genome measured_f0_median_hz (running-speech median)
F0_TOL = 3.0
ANCHOR_TOL_PCT = 5.0
# SUB_LEVEL_TARGET removed in Round 14: target is read from the genome
# (sub_target in run()). Kept out to avoid a second source of truth.
SUB_LEVEL_TOL = 3.0
F0_CAPTURE_TOL_HZ = 2.0   # rendered F0 must stay this close to no-sub baseline


def slug(text):
    return (text.replace(" ", "_").replace(".", "").replace("!", "")
            .replace("?", "").replace(",", "").lower())


def measure(path):
    """HEARING's instrument: tilt / f0 / hnr."""
    from autonomous_eval import measure_render
    return measure_render(path)


def audio_track_fidelity(plan, audio):
    """|F0 in rendered AUDIO - planned F0 track| at anchor times, in %.

    Round 13 §2.8 / E4: the old 'anchor' check compared the F0 TRACK to the
    planner's absolute anchors, neither of which touched audio, so it could
    never catch a renderer that ignored the track. This measures the AUDIO
    (via Praat) against the plan track instead — audio vs plan, which can
    genuinely fail. Option B ruling: anchors are descriptive, so they are not
    the reference; the composed track is.
    """
    import parselmouth
    n = max(int(max((s.t1 for s in plan.segments), default=1.0) * SR) + 240, len(audio))
    track = build_f0_track(plan, n)
    # Round 14 Q2: anchors alone are tail-biased ("moon" has 2 anchors at
    # 78%/86% of the utterance, first 78% unchecked). Probe a uniform grid
    # across each voiced region too, keeping strict None-on-unvoiced.
    times = [a.t for a in plan.f0_anchors]
    for seg in plan.segments:
        if seg.voiced and seg.kind != "silence":
            dur = seg.t1 - seg.t0
            if dur > 0.05:
                for q in (0.25, 0.5, 0.75):
                    times.append(seg.t0 + q * dur)
    times = sorted(set(round(t, 4) for t in times))
    if not times:
        return None
    snd = parselmouth.Sound(audio, sampling_frequency=SR)
    pit = snd.to_pitch(time_step=0.001, pitch_floor=75, pitch_ceiling=600)
    vals = pit.selected_array["frequency"]
    tt = pit.xs()
    errs = []
    for t in times:
        i = max(0, min(n - 1, int(round(t * SR))))
        planned = track[i]
        mask = (tt >= t - 0.03) & (tt <= t + 0.03) & np.isfinite(vals) & (vals > 0)
        if not mask.any():
            continue  # this probe unvoiced; strict majority check below
        realized = float(np.median(vals[mask]))
        errs.append(abs(realized - planned) / planned * 100.0)
    # Round 14 Q2: with a full-utterance grid, require a majority of probes to
    # be voiced. Silence / dropped renderer -> few voiced -> None -> FAIL.
    # A partial subset cannot sneak through (need >=60% of probes voiced).
    if len(errs) < 0.6 * len(times):
        return None
    return float(np.median(errs))


def sub_bass_levels(plan, audio):
    """Spectral sub/fund ratio, plus the carrier's own peak level."""
    n = max(int(max((s.t1 for s in plan.segments), default=1.0) * SR) + 240, len(audio))
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
    # Vacuous-pass guard (Round 13 §2.8): a failed measure returns 0.0.
    # If both F0s are 0, deviation is 0 and the check would pass on silence.
    if with_sub < 50 or no_sub < 50:
        raise RuntimeError(f"F0 measure missing: with_sub={with_sub}, no_sub={no_sub}")
    return with_sub - no_sub, with_sub, no_sub


def run(quiet=False):
    genome = load_genome(os.path.join(REPO, "genome", "voice_genome.yaml"))
    # Genome is the single source of truth for the carrier target (Round 13 §2.3).
    sub_target = float(genome["effects"]["sub_bass"]["level_db"])
    os.makedirs(OUT_DIR, exist_ok=True)

    rows = []
    for text in GOLDEN_SENTENCES:
        plan = build_plan(text)
        audio = render_plan_v3(plan, genome)
        path = os.path.join(OUT_DIR, slug(text) + ".wav")
        wavfile.write(path, SR, (audio * 32767).astype(np.int16))

        m = measure(path)
        carrier_db, spec_db = sub_bass_levels(plan, audio)
        cap_dev, f0_with, f0_base = f0_capture_deviation(plan, audio)
        track_err = audio_track_fidelity(plan, audio)

        rows.append({
            "text": text,
            "tilt_db_oct": round(float(m.get("tilt", 0.0)), 3),
            "f0_hz": round(float(m.get("f0", 0.0)), 2),  # mean, informational
            "f0_median_hz": round(float(m.get("f0_median", 0.0)), 2),
            "f0_p05_hz": round(float(m.get("f0_p05", 0.0)), 2),
            "f0_p95_hz": round(float(m.get("f0_p95", 0.0)), 2),
            "hnr_db": round(float(m.get("hnr", 0.0)), 2),
            "audio_track_err_pct": round(float(track_err), 2) if track_err is not None else None,
            "sub_carrier_db": round(carrier_db, 2),
            "sub_fund_db": round(spec_db, 2),
            "f0_capture_dev_hz": round(float(cap_dev), 2),
            "f0_no_sub_hz": round(float(f0_base), 2),
        })

    tilts = [r["tilt_db_oct"] for r in rows]
    f0s = [r["f0_median_hz"] for r in rows]  # true median, not the mean
    med_tilt = float(np.median(tilts))
    med_f0 = float(np.median(f0s))
    track_errs = [r["audio_track_err_pct"] for r in rows
                  if r["audio_track_err_pct"] is not None]
    med_track_err = float(np.median(track_errs)) if track_errs else None
    carriers = [r["sub_carrier_db"] for r in rows]
    med_carrier = float(np.median(carriers))
    cap_devs = [abs(r["f0_capture_dev_hz"]) for r in rows]
    worst_capture = float(max(cap_devs)) if cap_devs else None

    checks = {
        # Round 13 E7 ruling: tilt on raw speech is informational, NOT an
        # identity gate. The -1.30 target was measured as a speech PSD median,
        # but Zar E2 and my own measurement agree the band is formant-dominated
        # (per-sentence -2.7..-8.0 on stable source tilt). A true dB/oct
        # cascade forces the median to -1.29 but drops HEARING's canonical
        # composite 0.815->0.505 on "moon" (MFCC/formant match breaks). The
        # source tilt is the real lever and is not yet targeted. Report the
        # value; do not veto on it. This can fail to report (value=None).
        "tilt_median": {
            "value": round(med_tilt, 3), "target": TILT_TARGET,
            "tol": TILT_TOL,
            "pass": True,
            "informational": True,
            "note": "formant-dominated on speech; not a gate until a source-level target exists",
        },
        "f0_median": {
            "value": round(med_f0, 2), "target": F0_TARGET,
            "tol": F0_TOL,
            "pass": abs(med_f0 - F0_TARGET) <= F0_TOL,
        },
        "audio_track_fidelity": {
            "value": round(med_track_err, 2) if med_track_err is not None else None,
            "target_max_pct": ANCHOR_TOL_PCT,
            "pass": (med_track_err is not None and med_track_err <= ANCHOR_TOL_PCT),
        },
        "sub_bass_carrier": {
            "value": round(med_carrier, 2), "target": sub_target,
            "tol": SUB_LEVEL_TOL,
            "pass": abs(med_carrier - sub_target) <= SUB_LEVEL_TOL,
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
        print(f"{'sentence':42s} {'tilt':>7s} {'f0med':>7s} {'hnr':>7s} "
              f"{'trk%':>7s} {'subdB':>7s}")
        for r in rows:
            am = r["audio_track_err_pct"]
            print(f"{r['text'][:40]:42s} {r['tilt_db_oct']:7.2f} "
                  f"{r['f0_median_hz']:7.1f} {r['hnr_db']:7.2f} "
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
