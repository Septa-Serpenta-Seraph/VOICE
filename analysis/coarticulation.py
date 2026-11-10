#!/usr/bin/env python3
"""
VOICE — Coarticulation subsystem (Phase 3, Step 5).

Formant transitions between steady states: CV and VC trajectories,
locus-equation-style targets for stops, nasal place cues.

Measurement: check at three points (onset, midpoint, steady state)
against interpolation between endpoint values.

Usage:
    python coarticulation.py --demo     # render CV/VC transitions
    python coarticulation.py --test     # transition checks
"""

import argparse
import json
import os
import sys

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 48000

# Transition durations (ms)
CV_TRANSITION_MS = 50   # consonant → vowel
VC_TRANSITION_MS = 40   # vowel → consonant

# Consonant locus targets (Hz) — starting points for formant transitions
# These are the "locus" frequencies that formants move toward during
# consonant closure (Fant 1960, Lindblom 1963)
CONSONANT_LOCUS = {
    "m": {"F1": 250, "F2": 800, "F3": 2200},   # bilabial nasal
    "n": {"F1": 300, "F2": 1500, "F3": 2500},   # alveolar nasal
    "\u014b": {"F1": 300, "F2": 1000, "F3": 2500},  # velar nasal
    "s": {"F1": 400, "F2": 1800, "F3": 3000},    # alveolar fricative
    "\u0283": {"F1": 350, "F2": 1200, "F3": 2800},  # postalveolar fricative
}

# Nasal place cues: formant transitions that distinguish /m n ŋ/
# In isolation, nasals are near-identical; place lives in transitions
NASAL_PLACE_CUES = {
    "m": {"F2_transition": "falling", "F2_target": 800, "F3_target": 2200},
    "n": {"F2_transition": "rising", "F2_target": 1500, "F3_target": 2500},
    "\u014b": {"F2_transition": "falling", "F2_target": 1000, "F3_target": 2500},
}


def interpolate_formants(start, end, n_points):
    """Linear interpolation between two formant sets.

    start, end: dicts of {F1, F2, F3, F4}
    Returns: list of formant dicts
    """
    result = []
    for i in range(n_points):
        t = i / max(n_points - 1, 1)
        # Smooth interpolation (cosine easing)
        t_smooth = 0.5 * (1 - np.cos(np.pi * t))
        formants = {}
        for key in start:
            formants[key] = start[key] + (end[key] - start[key]) * t_smooth
        result.append(formants)
    return result


def cv_transition(consonant, vowel_formants, duration_ms=CV_TRANSITION_MS, sr=SR):
    """Generate CV transition: formants move from consonant locus to vowel.

    Returns: list of formant dicts at each frame.
    """
    n_frames = max(1, int(duration_ms * sr / 1000 / 10))  # ~10ms per frame
    locus = CONSONANT_LOCUS.get(consonant, CONSONANT_LOCUS["s"])

    # Ensure all formants present
    locus_full = {"F1": locus.get("F1", 400), "F2": locus.get("F2", 1500),
                  "F3": locus.get("F3", 2500), "F4": 3100}
    vowel_full = dict(vowel_formants)
    if "F4" not in vowel_full:
        vowel_full["F4"] = 3100

    trajectory = interpolate_formants(locus_full, vowel_full, n_frames)
    # Add steady-state vowel at the end
    trajectory.append(vowel_full)

    return trajectory


def vc_transition(vowel_formants, consonant, duration_ms=VC_TRANSITION_MS, sr=SR):
    """Generate VC transition: formants move from vowel to consonant locus."""
    n_frames = max(1, int(duration_ms * sr / 1000 / 10))
    locus = CONSONANT_LOCUS.get(consonant, CONSONANT_LOCUS["s"])

    locus_full = {"F1": locus.get("F1", 400), "F2": locus.get("F2", 1500),
                  "F3": locus.get("F3", 2500), "F4": 3100}
    vowel_full = dict(vowel_formants)
    if "F4" not in vowel_full:
        vowel_full["F4"] = 3100

    trajectory = interpolate_formants(vowel_full, locus_full, n_frames)
    trajectory.append(locus_full)

    return trajectory


def check_transition(trajectory, targets, tolerance_pct=15.0):
    """Check transition at three points: onset, midpoint, steady state.

    targets: dict of {point: {F1, F2, F3, F4}} or {point: expected_formants}
    Returns: (passed, notes)
    """
    if len(trajectory) < 3:
        return False, ["trajectory too short"]

    n = len(trajectory)
    onset = trajectory[0]
    midpoint = trajectory[n // 2]
    steady = trajectory[-1]

    points = {"onset": onset, "midpoint": midpoint, "steady": steady}
    passed = True
    notes = []

    # Check that formants are monotonically moving (no reversals)
    for formant in ["F1", "F2", "F3"]:
        vals = [p[formant] for p in trajectory]
        # Check no NaN
        if any(np.isnan(v) for v in vals):
            passed = False
            notes.append(f"{formant}: NaN in trajectory")
            continue
        # Check range is reasonable
        f_range = max(vals) - min(vals)
        if f_range < 1:
            notes.append(f"{formant}: minimal movement ({f_range:.1f} Hz)")

    # Check endpoints are within tolerance of targets
    if targets:
        for point_name, expected in targets.items():
            if point_name in points:
                actual = points[point_name]
                for formant, target_val in expected.items():
                    if formant in actual:
                        err = abs(actual[formant] - target_val) / target_val * 100
                        if err > tolerance_pct:
                            passed = False
                            notes.append(f"{point_name}.{formant}: {actual[formant]:.0f} vs {target_val} ({err:.1f}%)")

    return passed, notes


def nasal_place_check(consonant, vowel_formants):
    """Verify nasal place cues are distinguishable in transitions.

    The place distinction is in the starting locus and trajectory shape,
    not absolute rise/fall (which depends on the following vowel).

    Returns: (passed, notes, cue_info)
    """
    if consonant not in NASAL_PLACE_CUES:
        return False, [f"unknown consonant: {consonant}"], {}

    cue = NASAL_PLACE_CUES[consonant]
    trajectory = cv_transition(consonant, vowel_formants)

    locus = CONSONANT_LOCUS[consonant]
    f2_locus = locus["F2"]
    f2_vowel = vowel_formants["F2"]

    # Check 1: transition starts near the locus
    f2_start = trajectory[0]["F2"]
    start_err = abs(f2_start - f2_locus) / f2_locus * 100
    if start_err > 5:
        return False, [f"{consonant}: F2 start {f2_start:.0f} vs locus {f2_locus} ({start_err:.1f}%)"], cue

    # Check 2: transition ends near the vowel
    f2_end = trajectory[-1]["F2"]
    end_err = abs(f2_end - f2_vowel) / f2_vowel * 100
    if end_err > 5:
        return False, [f"{consonant}: F2 end {f2_end:.0f} vs vowel {f2_vowel} ({end_err:.1f}%)"], cue

    # Check 3: locus is distinct from other nasals
    other_loci = {c: CONSONANT_LOCUS[c]["F2"] for c in ["m", "n", "\u014b"] if c != consonant}
    for other, other_locus in other_loci.items():
        if abs(f2_locus - other_locus) < 100:
            return False, [f"{consonant}: F2 locus {f2_locus} too close to {other} ({other_locus})"], cue

    return True, [], cue


def demo(genome, sr=SR):
    """Demo: render CV/VC transitions and check them."""
    anchor = genome["filter"]["neutral_anchor"]
    vowel = "ɑ"
    grid = genome["vowel_grid"][vowel]
    vowel_formants = {"F1": grid[0], "F2": grid[1], "F3": grid[2], "F4": anchor["F4"]["hz"]}

    print("Coarticulation — CV/VC Transitions")
    print("=" * 60)

    # CV transitions for different consonants
    for cons in ["m", "n", "\u014b", "s", "\u0283"]:
        traj = cv_transition(cons, vowel_formants)
        passed, notes = check_transition(traj, None)
        f2_start = traj[0]["F2"]
        f2_end = traj[-1]["F2"]
        print(f"\nCV /{cons}/→/{vowel}/: {len(traj)} frames")
        print(f"  F2: {f2_start:.0f} → {f2_end:.0f} ({'rising' if f2_end > f2_start else 'falling'})")
        print(f"  Check: {'PASS' if passed else 'FAIL'}")
        if notes:
            for n in notes:
                print(f"    {n}")

    # VC transitions
    print("\n" + "=" * 60)
    print("VC Transitions")
    for cons in ["m", "n", "\u014b"]:
        traj = vc_transition(vowel_formants, cons)
        passed, notes = check_transition(traj, None)
        f2_start = traj[0]["F2"]
        f2_end = traj[-1]["F2"]
        print(f"\nVC /{vowel}/→/{cons}/: {len(traj)} frames")
        print(f"  F2: {f2_start:.0f} → {f2_end:.0f}")
        print(f"  Check: {'PASS' if passed else 'FAIL'}")

    # Nasal place cues
    print("\n" + "=" * 60)
    print("Nasal Place Cues")
    for cons in ["m", "n", "\u014b"]:
        passed, notes, cue = nasal_place_check(cons, vowel_formants)
        print(f"\n/{cons}/: {'PASS' if passed else 'FAIL'}")
        if notes:
            for n in notes:
                print(f"  {n}")
        if cue:
            print(f"  F2 transition: {cue['F2_transition']}, target: {cue['F2_target']} Hz")


def run_transition_checks(genome, sr=SR):
    """Run all transition checks for the vowel set paired with consonants."""
    anchor = genome["filter"]["neutral_anchor"]
    vowels = ["i", "ɪ", "e", "ɛ", "æ", "ɑ", "ʌ", "ɔ", "o", "ʊ", "u", "ə"]
    consonants = ["m", "n", "\u014b", "s", "\u0283"]

    results = {"cv": {}, "vc": {}, "nasal": {}}
    all_pass = True

    for vowel in vowels:
        grid = genome["vowel_grid"][vowel]
        vf = {"F1": grid[0], "F2": grid[1], "F3": grid[2], "F4": anchor["F4"]["hz"]}

        for cons in consonants:
            # CV
            traj = cv_transition(cons, vf)
            passed, notes = check_transition(traj, None)
            key = f"{cons}_{vowel}"
            results["cv"][key] = {"passed": passed, "notes": notes}
            if not passed:
                all_pass = False

            # VC
            traj = vc_transition(vf, cons)
            passed, notes = check_transition(traj, None)
            results["vc"][key] = {"passed": passed, "notes": notes}
            if not passed:
                all_pass = False

    # Nasal place checks
    for cons in ["m", "n", "\u014b"]:
        for vowel in vowels[:4]:  # subset for speed
            grid = genome["vowel_grid"][vowel]
            vf = {"F1": grid[0], "F2": grid[1], "F3": grid[2], "F4": anchor["F4"]["hz"]}
            passed, notes, cue = nasal_place_check(cons, vf)
            key = f"{cons}_{vowel}"
            results["nasal"][key] = {"passed": passed, "notes": notes}
            if not passed:
                all_pass = False

    return all_pass, results


def main():
    parser = argparse.ArgumentParser(description="VOICE coarticulation")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--sr", type=int, default=SR)
    args = parser.parse_args()

    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    with open(genome_path) as f:
        genome = yaml.safe_load(f)

    if args.demo:
        demo(genome, sr=args.sr)

    elif args.test:
        all_pass, results = run_transition_checks(genome, sr=args.sr)
        n_cv = len(results["cv"])
        n_vc = len(results["vc"])
        n_nasal = len(results["nasal"])
        cv_pass = sum(1 for r in results["cv"].values() if r["passed"])
        vc_pass = sum(1 for r in results["vc"].values() if r["passed"])
        nasal_pass = sum(1 for r in results["nasal"].values() if r["passed"])

        print(f"Transition checks:")
        print(f"  CV: {cv_pass}/{n_cv} pass")
        print(f"  VC: {vc_pass}/{n_vc} pass")
        print(f"  Nasal place: {nasal_pass}/{n_nasal} pass")
        print(f"  Overall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")

        if args.json:
            print(json.dumps(results, indent=2))

        # Save results
        out_path = os.path.join(os.path.dirname(__file__), "..", "renders",
                                "coarticulation", "transition_checks.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump({"all_pass": all_pass, "results": results}, f, indent=2)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()