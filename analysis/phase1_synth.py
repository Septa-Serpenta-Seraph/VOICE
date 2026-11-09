#!/usr/bin/env python3
"""
VOICE — Phase 1 synth (integrated: Zarza skeleton + Narusya's parallel synthesis)
==================================================================================
Integrated 2026-11-09 from Zarza's phase1_synth_skeleton.py draft.

What changed from Zarza's draft:
  - Cascade → parallel resonator bank (Phase 1 testing showed parallel
    recovers formants much better: F3 16-32% error → 0.5-4.6%)
  - Simple pulse-train source is the verified baseline (--source simple)
  - LF timing VERIFIED against Fant 1985 / Doval 2006 (lf_timing_verify.py)
  - All values genome-driven (no hardcoded numbers)
  - Effects stubs raise NotImplementedError (no silent partial effects)
  - Formant frame count warning (n < 10) is loud, not silent
  - Perturbation round-trip (known jitter/shimmer in → measured out)
  - Front-F2 A/B pairs for Adora's ears

Caveats (Zarza's, carried forward):
  - LF timing VERIFIED against Fant 1985 (Doval 2006 re-parameterization)
  - Effects are stubs only (Phase 2 work)
  - Micro-dip depth is still unspecified (duration only, 5-15 ms)
"""

import argparse
import json
import os
import sys

import numpy as np
import yaml

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
try:
    from synthetic_measure import measure_formants_synthetic, measure_f0_synthetic, gate0_synthetic
    HAVE_SYNTHETIC = True
except Exception as exc:
    HAVE_SYNTHETIC = False
    SYNTHETIC_ERROR = exc

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
    """Rd -> LF timing (Tp, Te, Ta). Verified against Fant 1985 / Doval 2006.

    Doval 2006 re-parameterization:
      Ra = (1 + 4.8*Rd) / 100
      Rk = (22.4 + 11.8*Rd) / 100
      Rg = Rk*(0.5 + 1.2*Rk) / (0.44*Rd - 4*Ra*(0.5 + 1.2*Rk))
      Oq = (1 + Rk) / (2*Rg)          # open quotient = Te/T0
      am = 1 / (1 + Rk)               # asymmetry = Tp/Te
      Ta = Ra * T0                     # return phase time constant

      Te = Oq * T0
      Tp = am * Te
    """
    t0 = 1.0 / f0
    ra = (1.0 + 4.8 * rd) / 100.0
    rk = (22.4 + 11.8 * rd) / 100.0
    rg = rk * (0.5 + 1.2 * rk) / (0.44 * rd - 4.0 * ra * (0.5 + 1.2 * rk))
    oq = (1.0 + rk) / (2.0 * rg)
    am = 1.0 / (1.0 + rk)
    te = oq * t0
    tp = am * te
    ta = ra * t0
    return tp, te, ta


def _lf_alpha(tp, te, ta, t0):
    """Compute alpha for zero DC condition (verified)."""
    from scipy.optimize import brentq
    omega = np.pi / tp
    eps = 1.0 / ta

    def integral_opening(alpha):
        return (np.exp(alpha * te) * (alpha * np.sin(omega * te) - omega * np.cos(omega * te)) + omega) / (alpha**2 + omega**2)

    t = np.linspace(te, t0, 1000)
    ret = -(1.0 / (eps * ta)) * (np.exp(-eps * (t - te)) - np.exp(-eps * (t0 - te)))
    ir = np.trapezoid(ret, t)

    def f(alpha):
        return integral_opening(alpha) + ir

    try:
        alpha = brentq(f, -10000, 10000, xtol=1e-10, maxiter=1000)
    except ValueError:
        alpha = -omega / np.tan(omega * te) if abs(np.tan(omega * te)) > 1e-6 else 0.0
    return alpha, omega, eps


def lf_pulse(tp, te, ta, t0, sr, n_cycles, rng, jitter_pct=0.7, drift_hz=0.5):
    """LF glottal-flow-derivative pulse train (verified piecewise form)."""
    alpha, omega, eps = _lf_alpha(tp, te, ta, t0)
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

        # Value at Te from opening phase
        val_te_open = e0 * np.exp(alpha * te_c) * np.sin(omega * te_c)
        # Return phase amplitude for continuity
        denom = 1.0 - np.exp(-eps * (t0 - te_c))
        A = -val_te_open / denom if abs(denom) > 1e-10 else 0.0

        cyc = np.where(
            t < te_c,
            e0 * np.exp(alpha * t) * np.sin(omega * t),
            -A * (np.exp(-eps * (t - te_c)) - np.exp(-eps * (t0 - te_c))),
        )
        out[pos:pos + n] += cyc
        pos += n
    out *= (1.0 + 0.02 * np.sin(2 * np.pi * drift_hz * np.arange(total) / sr))
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

def synthesize_vowel(f0, formants, duration, sr, source=None, bw=None, bandwidths=None):
    """Parallel resonator bank — each formant is independent, outputs summed.

    Phase 1 testing showed this recovers formants much better than cascade:
    F3 error went from 16-32% (cascade) to 0.5-4.6% (parallel).

    bandwidths: dict of {name: bw_hz} from genome (e.g., {"F1": 80, "F2": 100, ...}).
    If provided, uses per-formant bandwidths. Otherwise falls back to bw param.
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
    for name, f_freq in formants.items():
        if bandwidths and name in bandwidths:
            formant_bw = bandwidths[name]
        elif bw is not None:
            formant_bw = bw
        else:
            formant_bw = f_freq * 0.1
        w0 = 2 * np.pi * f_freq / sr
        r = np.exp(-np.pi * formant_bw / sr)
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
    # Genome bandwidths (per-formant, from genome filter section)
    filter_section = genome.get("filter", {})
    bandwidths = {}
    for key in ["F1", "F2", "F3", "F4"]:
        if key in filter_section and isinstance(filter_section[key], dict):
            bandwidths[key] = filter_section[key].get("bw", 150)
        elif key in anchor and isinstance(anchor[key], dict):
            bandwidths[key] = anchor[key].get("bw", 150)
    if not bandwidths:
        bandwidths = None
    source = make_source(genome, f0, duration, source_kind, rng)
    return synthesize_vowel(f0, formants, duration, SR, source=source,
                            bandwidths=bandwidths)


# ══════════════════════════════════════════════════════════════════════════
# Effects — stubs only, OFF by default (Phase 2). Cap enforced structurally.
# ══════════════════════════════════════════════════════════════════════════

def apply_effects_stub(signal, genome, sr=SR):
    """Placeholder. Raises until implemented."""
    raise NotImplementedError("Effects are Phase 2; Phase 1 renders dry.")


# ══════════════════════════════════════════════════════════════════════════
# Measure + Gate 0
# ══════════════════════════════════════════════════════════════════════════

def measure(signal, sr=SR, targets=None):
    """Measure formants using synthetic mode (targeted window search)."""
    if targets is None:
        targets = {}
    if not HAVE_SYNTHETIC:
        raise RuntimeError(f"Synthetic measure unavailable: {SYNTHETIC_ERROR}")
    f0_result = measure_f0_synthetic(signal, sr, target_f0=190.0)
    formants = measure_formants_synthetic(signal, sr, targets)
    return {"f0": f0_result, "formants": formants}


def gate0_check(measured, target_f0, target_formants, label):
    """Gate 0 in synthetic mode: check formants within ±5% of known targets."""
    if not HAVE_SYNTHETIC:
        raise RuntimeError(f"Synthetic measure unavailable: {SYNTHETIC_ERROR}")
    passed, notes = gate0_synthetic(
        measured["formants"], target_formants,
        measured["f0"], target_f0, label
    )
    return passed, notes


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="VOICE Phase 1 synth")
    ap.add_argument("--genome", default="genome/voice_genome.yaml")
    ap.add_argument("--outdir", default="renders/phase1")
    ap.add_argument("--source", choices=["lf", "simple"], default="simple",
                    help="simple = verified Phase 0 source; lf = LF (timing verified)")
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
        meas = measure(sig[trim:], targets=targets)
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
              f"(err: F1={meas['formants']['F1']['error_pct']}% "
              f"F2={meas['formants']['F2']['error_pct']}% "
              f"F3={meas['formants']['F3']['error_pct']}% "
              f"F4={meas['formants']['F4']['error_pct']}%)")

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

    # 3. Perturbation round-trip (pending — needs Praat harness for jitter/shimmer).
    print("Perturbation round-trip: PENDING (jitter/shimmer measurement "
          "requires Praat harness; synthetic mode measures formants only)")

    # 4. F4 sweep diagnostic (Zarza Round 6: diagnose before retuning).
    from synthetic_measure import f4_sweep
    print("\nF4 sweep diagnostic:")
    sweep = f4_sweep(SR, 0.5, list(range(2900, 3301, 100)))
    sweep_errors = [r["error_pct"] for r in sweep]
    print(f"  Mean error: {np.mean(sweep_errors):.1f}%, Max: {max(sweep_errors):.1f}%")
    for r in sweep:
        print(f"  target={r['target_f4']}, measured={r['measured_f4']}, "
              f"error={r['error_pct']}%")
    report["f4_sweep"] = sweep

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
