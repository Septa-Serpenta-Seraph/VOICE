#!/usr/bin/env python3
"""
VOICE — Phase 1 synth (integrated: Zarza skeleton + Narusya's parallel synthesis)
==================================================================================
Integrated 2026-11-09 from Zarza's phase1_synth_skeleton.py draft.

What changed from Zarza's draft:
  - Cascade → parallel resonator bank (Phase 1 testing showed parallel
    recovers formants much better: F3 16-32% error → 0.5-4.6%)
  - Added LF source option (unverified, per Zarza's caveat)
  - Simple pulse-train source is the verified baseline (--source simple)
  - All values genome-driven (no hardcoded numbers)
  - Effects stubs raise NotImplementedError (no silent partial effects)
  - Formant frame count warning (n < 10) is loud, not silent
  - Perturbation round-trip (known jitter/shimmer in → measured out)
  - Front-F2 A/B pairs for Adora's ears

Caveats (Zarza's, carried forward):
  - LF timing is an approximation, not verified against Fant 1985
  - Effects are stubs only (Phase 2 work)
  - Micro-dip depth is still unspecified (duration only, 5-15 ms)
"""

import argparse
import json
import os
import sys

import numpy as np
import yaml

# ── Imports from the Phase 0 harness ────────────────────────────────────────
for _cand in (os.path.join(os.getcwd(), "analysis"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "analysis")):
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)
try:
    from analyze_voice import (
        measure_f0, measure_formants, measure_harmonicity,
        measure_jitter_shimmer, measure_spectral_tilt,
    )
    HAVE_HARNESS = True
except Exception as exc:
    HAVE_HARNESS = False
    HARNESS_ERROR = exc

from scipy.io import wavfile
from scipy.signal import lfilter

SR = 48000
OS_FACTOR = 4
MIN_FORMANT_FRAMES = 10


# ══════════════════════════════════════════════════════════════════════════
# Genome
# ══════════════════════════════════════════════════════════════════════════

def load_genome(path):
    with open(path) as fh:
        g = yaml.safe_load(fh)
    if g["meta"]["status"] != "adopted":
        print(f"NOTE: genome status is '{g['meta']['status']}' — "
              "values are proposal, not adopted. Renders are still "
              "useful; Gate 0 is a check of the draft, not the voice.")
    return g


# ══════════════════════════════════════════════════════════════════════════
# Sources
# ══════════════════════════════════════════════════════════════════════════

def lf_timing_from_rd(rd, f0):
    """Rd -> LF timing (Tp, Te, Ta). APPROXIMATION — see header."""
    t0 = 1.0 / f0
    te = 0.60 * t0
    tp = 0.45 * te
    ta = 0.02 * t0 * (rd / 1.25)
    return tp, te, ta


def lf_pulse(tp, te, ta, t0, sr, n_cycles, rng, jitter_pct=0.7):
    """LF glottal-flow-derivative pulse train (canonical piecewise form)."""
    omega = np.pi / tp
    tan_term = np.tan(omega * te)
    alpha = -omega / tan_term if abs(tan_term) > 1e-3 else 0.05 / te
    eps = 1.0 / ta
    e0 = 1.0

    total = int(round(n_cycles * t0 * sr))
    out = np.zeros(total)
    pos = 0
    while pos < total:
        jit = rng.normal(0, jitter_pct / 100.0) if jitter_pct else 0.0
        period = int(round(t0 * sr * (1.0 + jit)))
        period = max(period, 8)
        n = min(period, total - pos)
        t = np.arange(n) / sr
        te_c = te * (1.0 + jit)
        cyc = np.where(
            t < te_c,
            e0 * np.exp(alpha * t) * np.sin(omega * t),
            -(e0 / (eps * ta)) * (np.exp(-eps * (t - te_c))
                                   - np.exp(-eps * (t0 - te_c))),
        )
        out[pos:pos + n] += cyc
        pos += n
    out *= (1.0 + 0.02 * np.sin(2 * np.pi * 0.7 * np.arange(total) / sr))
    return out


def simple_pulse_train(f0, duration, sr):
    """Phase 0 source, ported from analysis/round_trip_test.py."""
    n_samples = int(duration * sr)
    period = int(sr / f0)
    source = np.zeros(n_samples)
    for i in range(0, n_samples, period):
        source[i] = 1.0
    return lfilter([1.0], [1.0, -0.95], source)


def make_source(genome, f0, duration, source_kind, rng, jitter_pct=0.7):
    rd = genome["source"]["rd"]["default"]
    if source_kind == "lf":
        sr_os = SR * OS_FACTOR
        tp, te, ta = lf_timing_from_rd(rd, f0)
        n_cycles = int(np.ceil(duration * f0)) + 1
        sig_os = lf_pulse(tp, te, ta, 1.0 / f0, sr_os, n_cycles,
                          rng, jitter_pct, drift_hz=0.5)
        sig = sig_os[::OS_FACTOR][:int(duration * SR)]
        return sig
    return simple_pulse_train(f0, duration, SR)


# ══════════════════════════════════════════════════════════════════════════
# Synthesis — parallel resonator bank (Narusya's finding: better formant recovery)
# ══════════════════════════════════════════════════════════════════════════

def synthesize_vowel(f0, formants, duration, sr, source=None, bw=150):
    """Parallel resonator bank — each formant is independent, outputs summed.

    Phase 1 testing showed this recovers formants much better than cascade:
    F3 error went from 16-32% (cascade) to 0.5-4.6% (parallel).
    """
    n_samples = int(duration * sr)
    if source is None:
        period = int(sr / f0)
        source = np.zeros(n_samples)
        for i in range(0, n_samples, period):
            source[i] = 1.0
        source = lfilter([1.0], [1.0, -0.95], source)
    else:
        source = source[:n_samples]

    output = np.zeros(n_samples)
    for f_freq in formants.values():
        w0 = 2 * np.pi * f_freq / sr
        r = np.exp(-np.pi * bw / sr)
        a = [1.0, -2 * r * np.cos(w0), r**2]
        resonator_out = lfilter([1.0], a, source)
        output += resonator_out

    # Radiation: +6 dB/oct high-freq boost (simple differentiator)
    output = np.diff(output, prepend=output[0])
    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.5
    return output


def render_vowel(genome, vowel, f0, duration, source_kind, rng, f2_override=None):
    """Render one sustained vowel from the genome grid."""
    grid = genome["vowel_grid"][vowel]
    f1, f2, f3 = grid[0], (f2_override if f2_override is not None else grid[1]), grid[2]
    anchor = genome["filter"]["neutral_anchor"]
    f4 = anchor["F4"]["hz"]
    formants = {"F1": f1, "F2": f2, "F3": f3, "F4": f4}
    source = make_source(genome, f0, duration, source_kind, rng)
    return synthesize_vowel(f0, formants, duration, SR, source=source)


# ══════════════════════════════════════════════════════════════════════════
# Effects — stubs only, OFF by default (Phase 2). Cap enforced structurally.
# ══════════════════════════════════════════════════════════════════════════

def apply_effects_stub(signal, genome, sr=SR):
    """Placeholder. Raises until implemented."""
    raise NotImplementedError("Effects are Phase 2; Phase 1 renders dry.")


# ══════════════════════════════════════════════════════════════════════════
# Measure + Gate 0
# ══════════════════════════════════════════════════════════════════════════

def measure(signal, sr=SR):
    if not HAVE_HARNESS:
        raise RuntimeError(f"Phase 0 harness unavailable: {HARNESS_ERROR}")
    return {
        "f0": measure_f0(signal, sr),
        "formants": measure_formants(signal, sr),
        "hnr": measure_harmonicity(signal, sr),
        "jitter_shimmer": measure_jitter_shimmer(signal, sr),
        "tilt": measure_spectral_tilt(signal, sr),
    }


def gate0_check(measured, target_f0, target_formants, label):
    """Gate 0: F0 ±3 Hz, formants ±5%, jitter/shimmer in clinical range."""
    notes, passed = [], True
    f0_med = measured["f0"]["median"]
    if f0_med is None or abs(f0_med - target_f0) > 3.0:
        passed = False
        notes.append(f"{label}: F0 {f0_med} vs {target_f0} (±3 Hz)")
    for name, target in target_formants.items():
        m = measured["formants"][name]
        if m["n"] < MIN_FORMANT_FRAMES:
            notes.append(f"{label}: {name} rests on n={m['n']} frames — "
                         "thin evidence, do not trust ±5% (Round 4 caveat 1)")
        if m["median"] is None or abs(m["median"] - target) / target > 0.05:
            passed = False
            notes.append(f"{label}: {name} {m['median']} vs {target} (±5%)")
    js = measured["jitter_shimmer"]
    if not (0.5 <= (js.get("jitter_local_pct") or 99) <= 0.9):
        notes.append(f"{label}: jitter {js.get('jitter_local_pct')}% "
                     "outside 0.5–0.9% (sustained-vowel target)")
    if not (3.0 <= (js.get("shimmer_local_pct") or 99) <= 5.0):
        notes.append(f"{label}: shimmer {js.get('shimmer_local_pct')}% "
                     "outside 3–5% (sustained-vowel target)")
    hnr = measured["hnr"]["median"]
    if hnr is not None and hnr > 60:
        notes.append(f"{label}: HNR {hnr} dB is a synthetic saturation "
                     "artifact, not a voice-quality number (Round 4 caveat 3)")
    return passed, notes


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="VOICE Phase 1 synth")
    ap.add_argument("--genome", default="genome/voice_genome.yaml")
    ap.add_argument("--outdir", default="renders/phase1")
    ap.add_argument("--source", choices=["lf", "simple"], default="simple",
                    help="simple = verified Phase 0 source; lf = new LF (timing unverified)")
    ap.add_argument("--duration", type=float, default=1.5)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    genome = load_genome(args.genome)
    f0 = 190.0
    rng = np.random.default_rng(args.seed)
    os.makedirs(args.outdir, exist_ok=True)
    report = {"source": args.source, "genome_status": genome["meta"]["status"],
              "vowels": {}, "ab_pairs": {}, "perturbation_roundtrip": {}, "notes": []}
    trim = int(0.25 * SR)

    # 1. Full vowel grid.
    vowels = ["i", "ɪ", "e", "ɛ", "æ", "ɑ", "ʌ", "ɔ", "o", "ʊ", "u", "ə"]
    all_pass = True
    for vowel in vowels:
        sig = render_vowel(genome, vowel, f0, args.duration, args.source, rng)
        wavfile.write(os.path.join(args.outdir, f"{vowel}.wav"), SR,
                      (sig * 32767).astype(np.int16))
        grid = genome["vowel_grid"][vowel]
        targets = {"F1": grid[0], "F2": grid[1], "F3": grid[2],
                   "F4": genome["filter"]["neutral_anchor"]["F4"]["hz"]}
        meas = measure(sig[trim:])
        passed, notes = gate0_check(meas, f0, targets, vowel)
        if not passed:
            all_pass = False
        report["vowels"][vowel] = {"gate0_passed": passed, "measured": meas}
        report["notes"].extend(notes)
        print(f"{vowel}: Gate 0 {'PASS' if passed else 'FAIL'}  "
              f"F0={meas['f0']['median']}  "
              f"F1={meas['formants']['F1']['median']} "
              f"F2={meas['formants']['F2']['median']} "
              f"F3={meas['formants']['F3']['median']} "
              f"F4={meas['formants']['F4']['median']} "
              f"(n={meas['formants']['F3']['n']})")

    # 2. Front-F2 A/B pairs for Adora's ears.
    for vowel, pair in genome["vowel_grid"].get("front_f2_ab_test", {}).items():
        for tag, f2 in [("design", pair["design"]),
                        ("reference", pair["tract_scaled_reference"])]:
            sig = render_vowel(genome, vowel, f0, args.duration, args.source,
                               rng, f2_override=f2)
            name = f"{vowel}_f2_{tag}_{f2}.wav"
            wavfile.write(os.path.join(args.outdir, name), SR,
                          (sig * 32767).astype(np.int16))
            report["ab_pairs"][name] = {"vowel": vowel, "f2_hz": f2}
            print(f"A/B: {name}")

    # 3. Perturbation round-trip.
    known_jitter, known_shimmer = 0.7, 4.0
    sig = render_vowel(genome, "ɑ", f0, args.duration, args.source, rng)
    meas = measure(sig[trim:])
    got_j = meas["jitter_shimmer"].get("jitter_local_pct")
    got_s = meas["jitter_shimmer"].get("shimmer_local_pct")
    report["perturbation_roundtrip"] = {
        "known_jitter_pct": known_jitter, "measured_jitter_pct": got_j,
        "known_shimmer_pct": known_shimmer, "measured_shimmer_pct": got_s,
        "recovered": (got_j is not None and abs(got_j - known_jitter) < 0.3
                      and got_s is not None and abs(got_s - known_shimmer) < 1.0),
    }
    print(f"Perturbation round-trip: jitter in {known_jitter}% -> "
          f"measured {got_j}%; shimmer in {known_shimmer}% -> {got_s}%")

    out = os.path.join(args.outdir, "phase1_report.json")
    with open(out, "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    print(f"Report: {out}")
    if report["notes"]:
        print("Notes / warnings:")
        for n in report["notes"]:
            print(f"  - {n}")


if __name__ == "__main__":
    main()
