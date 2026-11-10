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
            duration = len(audio) / SR
            results.append({
                "text": text,
                "status": "OK",
                "duration_s": round(duration, 2),
                "segments": len(plan.segments),
                "anchors": len(plan.f0_anchors),
                "events": len(plan.events),
                "oov": plan.provenance.get("oov_words", []),
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

    # Basic property checks
    print("\nProperty checks:")
    for r in results:
        if r["status"] == "OK":
            assert r["duration_s"] > 0, f"Zero duration: {r['text']}"
            assert r["segments"] > 0, f"No segments: {r['text']}"
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