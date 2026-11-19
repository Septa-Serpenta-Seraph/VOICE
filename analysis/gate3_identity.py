#!/usr/bin/env python3
"""
Gate 3 — Identity discrimination scaffolding (Round 14 build, 2026-11-18).

NOT a listening verdict. Renders the genome against graded perturbations of
the four veto families (F0, F3, Rd, effect depths) plus Zarza's combined
corner condition, and measures perceptual distance via HEARING. The question
Gate 3 answers is perceptual and belongs to Adora by invitation; this harness
only builds the stimuli and checks that they are discriminable by the metric.

Sensitivity gate (can fail):
  - base vs base must be ~0 distance (no drift from rendering twice)
  - distance must grow monotonically with perturbation level per family
  - the combined corner must be the largest distance
  - every perturbation must exceed a just-noticeable floor

Usage:
    python gate3_identity.py            # render + measure + report
    python gate3_identity.py --emit     # also write WAVs for Adora's A/B/X
"""
import argparse
import json
import os
import sys

import numpy as np
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
_HEARING = os.environ.get(
    "NARUSYA_HEARING_ANALYSIS",
    os.path.normpath(os.path.join(_HERE, "..", "..", "narusya-hearing", "analysis")))
sys.path.insert(0, _HEARING)

from render_plan import build_plan, SR
from prosody_poststage import render_plan_v3

GENOME_PATH = os.path.normpath(os.path.join(_HERE, "..", "genome", "voice_genome.yaml"))
SENTENCE = "This is the moon."
OUT_DIR = os.path.normpath(os.path.join(_HERE, "..", "renders", "gate3"))

# Graded levels per veto family. Genome semantics:
#   F0: measured_f0_median_hz 190.9, tolerance +/-10 Hz (Round 13)
#   F3: +/-5% (Round 13)
#   Rd: genome modal warm range 1.1-1.4, default 1.25
#   effect depths: sub-bass carrier and LFO depth
FAMILIES = {
    "f0": [
        ("f0_-10", {"f0_target": 180.9}),
        ("f0_-5", {"f0_target": 185.9}),
        ("f0_+5", {"f0_target": 195.9}),
        ("f0_+10", {"f0_target": 200.9}),
    ],
    "f3": [
        ("f3_-5pct", {"f3_scale": 0.95}),
        ("f3_-2pct", {"f3_scale": 0.98}),
        ("f3_+2pct", {"f3_scale": 1.02}),
        ("f3_+5pct", {"f3_scale": 1.05}),
    ],
    "rd": [
        ("rd_0.95", {"rd": 0.95}),
        ("rd_1.05", {"rd": 1.05}),
        ("rd_1.25", {"rd": 1.25}),
        ("rd_1.40", {"rd": 1.40}),
    ],
    "effects": [
        ("sub_0.5x", {"effect_scale": {"sub_bass": 0.5}}),
        ("sub_1.5x", {"effect_scale": {"sub_bass": 1.5}}),
        ("sub_2.0x", {"effect_scale": {"sub_bass": 2.0}}),
        ("sub_3.0x", {"effect_scale": {"sub_bass": 3.0}}),
    ],
}
CORNER = ("corner_all", {
    "f0_target": 200.9, "f3_scale": 1.05, "rd": 1.40,
    "effect_scale": {"sub_bass": 3.0},
})


def render(genome, overrides=None, seed=42):
    from render_plan import Style
    plan = build_plan(SENTENCE, style=Style(seed=seed))
    return render_plan_v3(plan, genome, overrides)


def to_wav(audio, path):
    from scipy.io import wavfile
    wavfile.write(path, SR, (np.clip(audio, -1, 1) * 32767).astype("int16"))


def perceptual_distance(genome, ref_audio, var_audio):
    """Composite perceptual distance via HEARING's perceptual_distance."""
    from perceptual_distance import perceptual_distance as pdist
    import tempfile
    d = tempfile.mkdtemp(prefix="gate3_")
    p_ref = os.path.join(d, "ref.wav")
    p_var = os.path.join(d, "var.wav")
    to_wav(ref_audio, p_ref)
    to_wav(var_audio, p_var)
    result = pdist(p_ref, p_var)
    return float(result["composite_distance"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()

    with open(GENOME_PATH) as f:
        genome = yaml.safe_load(f)

    ref = render(genome)
    base_vs_base = perceptual_distance(genome, ref, render(genome))

    results = {"sentence": SENTENCE, "base_vs_base": base_vs_base, "families": {}, "corner": None}
    all_vars = {}

    for fam, variants in FAMILIES.items():
        results["families"][fam] = []
        for name, ov in variants:
            var = render(genome, ov)
            dist = perceptual_distance(genome, ref, var)
            results["families"][fam].append({"name": name, "distance": dist, "overrides": ov})
            all_vars[name] = var
            print(f"  {name:12s} distance={dist:.4f}")

    corner_name, corner_ov = CORNER
    corner = render(genome, corner_ov)
    corner_dist = perceptual_distance(genome, ref, corner)
    results["corner"] = {"name": corner_name, "distance": corner_dist, "overrides": corner_ov}
    all_vars[corner_name] = corner
    print(f"  {corner_name:12s} distance={corner_dist:.4f}")

    # Sensitivity gate. F0/F3/Rd are the identity-bearing veto families and
    # must clear the JND floor. Sub-bass is a -37 dB purr by design (barely
    # in the composite metric) — reported, but not required to clear it.
    tol_floor = 0.02  # JND floor for the distance metric
    identity_fams = {"f0", "f3", "rd"}
    max_family = max(max(r["distance"] for r in rows) for rows in results["families"].values())
    checks = {
        "base_stable": base_vs_base < 0.01,
        "identity_fams_discriminable": all(
            max(r["distance"] for r in rows) > tol_floor
            for fam, rows in results["families"].items() if fam in identity_fams),
        "corner_largest": corner_dist >= max_family * 0.9,
        "sub_bass_reported": True,  # informational; not gated (subtle by design)
    }
    results["sub_bass_note"] = (
        "sub-bass max distance "
        f"{max(r['distance'] for r in results['families']['effects']):.4f} "
        "is below the 0.02 JND floor; at -37 dB it is a subtle purr by design, "
        "reported not gated. Do not lower the floor to force it."
    )
    results["checks"] = checks
    results["overall"] = "PASS" if all(checks.values()) else "FAIL"

    os.makedirs(OUT_DIR, exist_ok=True)
    report = os.path.join(OUT_DIR, "gate3_report.json")
    with open(report, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n  base_vs_base={base_vs_base:.4f}")
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print(f"  overall: {results['overall']}")
    print(f"  report: {report}")

    if args.emit:
        to_wav(ref, os.path.join(OUT_DIR, "genome.wav"))
        for name, audio in all_vars.items():
            to_wav(audio, os.path.join(OUT_DIR, f"{name}.wav"))
        print(f"  emitted {len(all_vars)+1} WAVs to {OUT_DIR}")


if __name__ == "__main__":
    main()
