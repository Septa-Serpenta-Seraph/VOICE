#!/usr/bin/env python3
"""
VOICE — Phase 4 Step 7: Golden Set and Testing

Full pipeline test: text → plan → render → measure.
Golden set of sentences for regression testing.

Usage:
    python golden_set.py --run     # run all golden tests
    python golden_set.py --list    # list golden sentences
"""

import argparse
import json
import os
import sys

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_plan import build_plan, RenderPlan, SR
from lexicon import g2p_sentence, normalize_text
from frame_renderer import load_genome
from prosody_poststage import render_plan_v3

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "..", "tests", "golden_set.json")

# ── Golden sentences ─────────────────────────────────────────────────────

GOLDEN_SENTENCES = [
    # Short statements
    "This is the moon.",
    "She sees the sun.",
    # Question
    "What time is it?",
    "Is this the moon?",
    # Function-word dense
    "The cat sat on the mat.",
    # Long sentence
    "The quick brown fox jumps over the lazy dog.",
    # Numbers and abbreviations
    "Dr. Smith has 3 patients today.",
    # OOV names
    "Narusya speaks with Zarza.",
    # Punctuation variety
    "Hello, world! How are you?",
    # Stress contrast
    "I record the record.",
]


def run_golden():
    """Run all golden sentences through the pipeline."""
    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    genome = load_genome(genome_path)

    results = []
    for text in GOLDEN_SENTENCES:
        try:
            plan = build_plan(text)
            audio = render_plan_v3(plan, genome)
            # Truncation guard (Round 13 §2.1): the buffer must cover the
            # whole plan. Appended boundary silences are out of temporal
            # order, so segments[-1].t1 used to cut the utterance short.
            planned_end = max((s.t1 for s in plan.segments), default=0.0)
            rendered_end = len(audio) / SR
            assert abs(rendered_end - planned_end) < 0.05, (
                f"Truncated render: {text!r} rendered={rendered_end:.3f}s "
                f"planned={planned_end:.3f}s")
            # Normalization guard (Round 13 §2.2): no golden word may fall
            # through to OOV/rule_fallback, except the household names
            # served by the documented override dictionary.
            household = {"Narusya", "Zarza"}
            bad_oov = [w for w, p in plan.provenance.get("g2p_paths", {}).items()
                       if p in ("oov", "rule_fallback") and w not in household]
            assert not bad_oov, f"Unnormalized word fell through: {text!r}: {bad_oov}"
            # Idempotence: the same plan must render byte-identically twice.
            # The double-planner bug made the second render differ.
            audio2 = render_plan_v3(plan, genome)
            assert np.array_equal(audio, audio2), f"Non-idempotent render: {text!r}"
            # Phrase boundaries must produce real silence, not a pause event
            # that nothing renders.
            for b in plan.provenance.get("boundaries", []):
                sil = [s for s in plan.segments
                       if s.kind == "silence" and s.word == b["word"]]
                assert sil, f"Boundary not rendered as silence: {text!r} word {b['word']}"
                s0 = int((sil[0].t0 + 0.02) * SR)
                s1 = int((sil[0].t1 - 0.02) * SR)
                if s1 > s0:
                    rms = float(np.sqrt(np.mean(audio[s0:s1] ** 2)))
                    assert rms < 1e-3, f"Pause not silent: {text!r} rms={rms}"
            duration = len(audio) / SR
            results.append({
                "text": text,
                "status": "OK",
                "duration_s": round(duration, 2),
                "segments": len(plan.segments),
                "anchors": len(plan.f0_anchors),
                "events": len(plan.events),
                "oov": plan.provenance.get("oov_words", []),
                "unknown_phones": plan.provenance.get("unknown_phones", []),
                "g2p_paths": plan.provenance.get("g2p_paths", {}),
                "phones": [s.phone for s in plan.segments],
            })
            print(f"  OK  {text!r:45s} {duration:.2f}s  {len(plan.segments)} segs")
        except Exception as e:
            results.append({
                "text": text,
                "status": "FAIL",
                "error": str(e),
            })
            print(f"  FAIL {text!r:45s} {e}")

    # Save results
    os.makedirs(os.path.dirname(GOLDEN_PATH), exist_ok=True)
    with open(GOLDEN_PATH, "w") as f:
        json.dump({"sentences": GOLDEN_SENTENCES, "results": results}, f, indent=2)

    ok = sum(1 for r in results if r["status"] == "OK")
    print(f"\nGolden set: {ok}/{len(results)} passed")

    # Structural property checks. These must be able to FAIL. The v3/v4 bug
    # (a consonant branch that was a silent no-op) and the lexicon no-op both
    # passed the old "did it render" checks, so we assert on mechanism now.
    print("\nProperty checks:")
    for r in results:
        if r["status"] != "OK":
            continue
        assert r["duration_s"] > 0, f"Zero duration: {r['text']}"
        assert r["segments"] > 0, f"No segments: {r['text']}"
        assert not r["unknown_phones"], f"Unknown phones dropped: {r['text']}: {r['unknown_phones']}"
        # Every word in the golden set must resolve through a real lexicon
        # path. A rule_fallback on a household name is allowed only if it
        # survives in the override file (checked in a dedicated test below).
        bad_paths = [w for w, p in r.get("g2p_paths", {}).items()
                     if p in ("simple_rule",)]
        assert not bad_paths, f"Placeholder G2P path: {r['text']}: {bad_paths}"
    # Household names must come from the override dictionary, not fallback.
    names = [r for r in results if r["text"] == "Narusya speaks with Zarza."]
    if names:
        nr = names[0]
        if nr["status"] == "OK":
            for name in ("Narusya", "Zarza"):
                assert nr.get("g2p_paths", {}).get(name) == "override", (
                    f"Household name {name!r} is not from override dictionary")
    print("  All property checks passed")

    return results


def list_golden():
    """List golden sentences."""
    for i, text in enumerate(GOLDEN_SENTENCES, 1):
        print(f"  {i:2d}. {text}")


def main():
    parser = argparse.ArgumentParser(description="VOICE golden set")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.run:
        run_golden()
    elif args.list:
        list_golden()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()