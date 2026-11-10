#!/usr/bin/env python3
"""
VOICE — Phase 4: Render Plan (frame renderer, Step 1)

Dataclasses for the render plan, phone table, and JSON round-trip.
This is the foundation: everything downstream consumes a RenderPlan.

Usage:
    python render_plan.py --demo       # build a plan for "This is the moon."
    python render_plan.py --roundtrip   # verify JSON round-trip
"""

import argparse
import json
import os
import sys
import dataclasses
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 48000
FRAME_MS = 5.0  # parameter update interval

# ── Phone table (IPA keys) ────────────────────────────────────────────────
# Each phone: kind, voiced, and which synthesizer handles it.
# Vowels and diphthongs point at genome vowel_grid.
# Consonants: stops need closure/burst/VOT (Phase 4a), fricatives/nasals exist.

PHONE_TABLE = {
    # Vowels (from genome vowel_grid)
    "i":  {"kind": "vowel", "voiced": True, "synth": "vowel"},
    "ɪ":  {"kind": "vowel", "voiced": True, "synth": "vowel"},
    "e":  {"kind": "vowel", "voiced": True, "synth": "vowel"},
    "ɛ":  {"kind": "vowel", "voiced": True, "synth": "vowel"},
    "æ":  {"kind": "vowel", "voiced": True, "synth": "vowel"},
    "ɑ":  {"kind": "vowel", "voiced": True, "synth": "vowel"},
    "ʌ":  {"kind": "vowel", "voiced": True, "synth": "vowel"},
    "ɔ":  {"kind": "vowel", "voiced": True, "synth": "vowel"},
    "o":  {"kind": "vowel", "voiced": True, "synth": "vowel"},
    "ʊ":  {"kind": "vowel", "voiced": True, "synth": "vowel"},
    "u":  {"kind": "vowel", "voiced": True, "synth": "vowel"},
    "ə":  {"kind": "vowel", "voiced": True, "synth": "vowel"},
    # Diphthongs (single timing unit, onset + offset + reach)
    "aɪ": {"kind": "diphthong", "voiced": True, "synth": "diphthong", "onset": "ɑ", "offset": "ɪ", "reach": 0.7},
    "aʊ": {"kind": "diphthong", "voiced": True, "synth": "diphthong", "onset": "ɑ", "offset": "ʊ", "reach": 0.7},
    "ɔɪ": {"kind": "diphthong", "voiced": True, "synth": "diphthong", "onset": "ɔ", "offset": "ɪ", "reach": 0.7},
    "eɪ": {"kind": "diphthong", "voiced": True, "synth": "diphthong", "onset": "e", "offset": "ɪ", "reach": 0.6},
    "oʊ": {"kind": "diphthong", "voiced": True, "synth": "diphthong", "onset": "o", "offset": "ʊ", "reach": 0.6},
    # R-colored vowel (very common: "her", "water")
    "ɝ":  {"kind": "vowel", "voiced": True, "synth": "vowel", "f3_override": 1800},
    # Fricatives (exist in fricatives.py)
    "s":  {"kind": "fricative", "voiced": False, "synth": "fricative"},
    "z":  {"kind": "fricative", "voiced": True, "synth": "fricative"},
    "ʃ":  {"kind": "fricative", "voiced": False, "synth": "fricative"},
    "ʒ":  {"kind": "fricative", "voiced": True, "synth": "fricative"},
    "f":  {"kind": "fricative", "voiced": False, "synth": "fricative"},
    "v":  {"kind": "fricative", "voiced": True, "synth": "fricative"},
    "θ":  {"kind": "fricative", "voiced": False, "synth": "fricative"},
    "ð":  {"kind": "fricative", "voiced": True, "synth": "fricative"},
    "h":  {"kind": "fricative", "voiced": False, "synth": "fricative"},
    # Nasals (exist in nasals.py)
    "m":  {"kind": "nasal", "voiced": True, "synth": "nasal"},
    "n":  {"kind": "nasal", "voiced": True, "synth": "nasal"},
    "ŋ":  {"kind": "nasal", "voiced": True, "synth": "nasal"},
    # Stops (Phase 4a — provisional)
    "p":  {"kind": "stop", "voiced": False, "synth": "stop", "vot_ms": 60},
    "b":  {"kind": "stop", "voiced": True, "synth": "stop", "vot_ms": 10},
    "t":  {"kind": "stop", "voiced": False, "synth": "stop", "vot_ms": 70},
    "d":  {"kind": "stop", "voiced": True, "synth": "stop", "vot_ms": 20},
    "k":  {"kind": "stop", "voiced": False, "synth": "stop", "vot_ms": 80},
    "g":  {"kind": "stop", "voiced": True, "synth": "stop", "vot_ms": 30},
    # Affricates (Phase 4a — provisional)
    "tʃ": {"kind": "affricate", "voiced": False, "synth": "affricate"},
    "dʒ": {"kind": "affricate", "voiced": True, "synth": "affricate"},
    # Liquids and glides (Phase 4a — provisional)
    "l":  {"kind": "liquid", "voiced": True, "synth": "liquid"},
    "ɹ":  {"kind": "liquid", "voiced": True, "synth": "liquid", "f3_target": 1800},
    "w":  {"kind": "glide", "voiced": True, "synth": "glide"},
    "j":  {"kind": "glide", "voiced": True, "synth": "glide"},
    # Silence
    "sil": {"kind": "silence", "voiced": False, "synth": "silence"},
}

# ── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class Style:
    """Utterance-level style: register + effort."""
    register: str = "neutral"       # neutral, calm_authority, tenderness, wildfire
    register_scale: float = 1.0     # pitch range multiplier (0.7, 0.9, 1.1, 1.0)
    effort: float = 0.5            # 0.0 (whisper) to 1.0 (full)
    rate_wpm: float = 142.5        # 135-150
    seed: int = 42

    def __post_init__(self):
        # Register presets
        presets = {
            "neutral": (1.0, 0.5),
            "calm_authority": (0.7, 0.3),
            "tenderness": (0.9, 0.2),
            "wildfire": (1.1, 0.8),
        }
        if self.register in presets:
            self.register_scale, self.effort = presets[self.register]


@dataclass
class Segment:
    """One phone or silence in the render plan."""
    i: int
    phone: str
    kind: str
    t0: float               # seconds, absolute
    t1: float
    word: int               # index into plan words
    syll: int               # syllable index within word
    stress: int             # 0, 1, 2
    voiced: bool
    targets: dict = field(default_factory=dict)  # {"F1":..., "F2":..., ...}
    # Diphthong fields
    onset: Optional[str] = None
    offset: Optional[str] = None
    reach: float = 1.0


@dataclass
class Anchor:
    """F0 or effort anchor point."""
    t: float
    value: float
    reason: str              # accent, boundary_tone, reset, phrase_offset


@dataclass
class Event:
    """Pause or micro-dip event."""
    kind: str                # pause | micro_dip
    t: float
    duration_ms: float
    tier: str = ""           # clause | sentence


@dataclass
class RenderPlan:
    """Complete render plan — the only thing the audio side sees."""
    schema: str = "renderplan/1"
    text: str = ""
    genome_version: str = "0.3.4-phase3"
    inventory_version: str = "phone_table/1"
    style: Style = field(default_factory=Style)
    words: List[str] = field(default_factory=list)
    segments: List[Segment] = field(default_factory=list)
    f0_anchors: List[Anchor] = field(default_factory=list)
    effort_anchors: List[Anchor] = field(default_factory=list)
    events: List[Event] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "RenderPlan":
        d = json.loads(s)
        # Reconstruct nested dataclasses
        d["style"] = Style(**d["style"])
        d["segments"] = [Segment(**seg) for seg in d["segments"]]
        d["f0_anchors"] = [Anchor(**a) for a in d["f0_anchors"]]
        d["effort_anchors"] = [Anchor(**a) for a in d["effort_anchors"]]
        d["events"] = [Event(**e) for e in d["events"]]
        return cls(**d)


# ── Syllabification (simple English) ─────────────────────────────────────

VOWELS = set("iɪeɛæɑʌɔoʊuəɝaɪaʊɔɪeɪoʊ".split())  # simplified
# Actually, let's use a simpler approach: count vowel nuclei

def _is_vowel(phone: str) -> bool:
    return phone in PHONE_TABLE and PHONE_TABLE[phone]["kind"] in ("vowel", "diphthong")


def syllabify(phones: List[str]) -> List[List[str]]:
    """Group phones into syllables. One nucleus (vowel/diphthong) per syllable."""
    syllables = []
    current = []
    for p in phones:
        current.append(p)
        if _is_vowel(p):
            # End syllable after vowel + following consonants until next vowel
            syllables.append(current)
            current = []
    if current:
        # Trailing consonants attach to last syllable
        if syllables:
            syllables[-1].extend(current)
        else:
            syllables.append(current)
    return syllables if syllables else [phones]


# ── Simple G2P (rule-based, v1) ─────────────────────────────────────────

# Minimal English G2P for common words. This is a placeholder until CMUdict
# is integrated. Handles the golden set sentences.

SIMPLE_G2P = {
    "this": ["ð", "ɪ", "s"],
    "is": ["ɪ", "z"],
    "the": ["ð", "ə"],
    "moon": ["m", "u", "n"],
    "she": ["ʃ", "i"],
    "sees": ["s", "i", "z"],
    "sun": ["s", "ʌ", "n"],
    "is": ["ɪ", "z"],
    "a": ["ə"],
    "test": ["t", "ɛ", "s", "t"],
    "hello": ["h", "ə", "l", "oʊ"],
    "world": ["w", "ɜ", "ɹ", "l", "d"],
    "what": ["w", "ʌ", "t"],
    "time": ["t", "aɪ", "m"],
    "it": ["ɪ", "t"],
    "yes": ["j", "ɛ", "s"],
    "no": ["n", "oʊ"],
    "please": ["p", "l", "i", "z"],
    "thank": ["θ", "æ", "ŋ", "k"],
    "you": ["j", "u"],
}


def g2p_word(word: str) -> List[str]:
    """Convert a word to IPA phones. Falls back to letter-by-letter for OOV."""
    w = word.lower().strip(".,!?;:'\"()-")
    if w in SIMPLE_G2P:
        return list(SIMPLE_G2P[w])
    # Fallback: spell out (for acronyms) or letter-by-letter
    if w.isupper() and len(w) <= 4:
        return [c.lower() for c in w]  # spell out
    # Letter-by-letter fallback (very crude)
    result = []
    for ch in w:
        if ch in "aeiou":
            result.append("ə")
        elif ch.isalpha():
            result.append(ch)
    return result if result else ["ə"]


# ── Function words (demoted stress) ──────────────────────────────────────

FUNCTION_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "of", "in", "on", "at", "to",
    "for", "with", "by", "from", "as", "into", "through", "during", "before",
    "after", "above", "below", "between", "under", "over", "and", "but", "or",
    "nor", "so", "yet", "both", "either", "neither", "not", "only", "own",
    "same", "than", "too", "very", "just", "this", "that", "these", "those",
    "it", "its", "i", "me", "my", "we", "our", "you", "your", "he", "him",
    "his", "she", "her", "they", "them", "their",
}


# ── Prosody planner (simplified) ──────────────────────────────────────────

def plan_prosody(plan: RenderPlan) -> RenderPlan:
    """Assign durations, F0 anchors, pauses, and micro-dips to a plan.

    This is a simplified planner. Full prosody integration comes in Step 2.
    """
    # Duration model: base duration per phone class (ms)
    PHONE_DURATIONS_MS = {
        "vowel": 80, "diphthong": 120, "fricative": 90,
        "nasal": 70, "stop": 60, "affricate": 100,
        "liquid": 60, "glide": 50, "silence": 0,
    }

    rate_scale = 142.5 / plan.style.rate_wpm if plan.style.rate_wpm > 0 else 1.0
    t = 0.0
    for seg in plan.segments:
        if seg.kind == "silence":
            seg.t0 = t
            seg.t1 = t
            continue
        base_ms = PHONE_DURATIONS_MS.get(seg.kind, 70)
        # Stress scaling: stressed vowels longer
        if seg.stress >= 1:
            base_ms *= 1.3
        # Function words shorter
        word = plan.words[seg.word] if seg.word < len(plan.words) else ""
        if word.lower() in FUNCTION_WORDS:
            base_ms *= 0.85
        dur_s = base_ms * rate_scale / 1000.0
        seg.t0 = t
        seg.t1 = t + dur_s
        t = seg.t1

    # F0 anchors: one per stressed syllable + phrase boundaries
    anchor_hz = 190.0
    for seg in plan.segments:
        if seg.voiced and seg.stress >= 1:
            plan.f0_anchors.append(Anchor(
                t=(seg.t0 + seg.t1) / 2,
                value=anchor_hz * 1.08,  # +8% accent
                reason="accent",
            ))

    # Declination: last anchor in phrase falls to -15%
    if plan.f0_anchors:
        last = plan.f0_anchors[-1]
        plan.f0_anchors.append(Anchor(
            t=last.t + 0.1,
            value=anchor_hz * 0.85,  # -15%
            reason="declination_end",
        ))

    # Phrase-final lengthening on last syllable
    if plan.segments:
        last_seg = plan.segments[-1]
        if last_seg.kind in ("vowel", "diphthong"):
            dur = last_seg.t1 - last_seg.t0
            last_seg.t1 = last_seg.t0 + dur * 1.4
            # Shift subsequent (none, but good practice)
            t = last_seg.t1

    return plan


# ── Plan builder ─────────────────────────────────────────────────────────

def build_plan(text: str, style: Optional[Style] = None) -> RenderPlan:
    """Build a render plan from text."""
    if style is None:
        style = Style()

    plan = RenderPlan(text=text, style=style)

    # Normalize: split on whitespace, keep punctuation attached to words
    import re
    tokens = text.split()
    plan.words = [t.strip(".,!?;:'\"()") for t in tokens]

    # Determine sentence type
    sentence_type = "statement"
    if text.strip().endswith("?"):
        sentence_type = "question"
    elif text.strip().endswith("!"):
        sentence_type = "exclamation"

    plan.provenance = {
        "sentence_type": sentence_type,
        "g2p_path": "simple_rule",
        "oov_words": [],
    }

    # G2P each word
    seg_idx = 0
    word_idx = 0
    for token in tokens:
        word = token.strip(".,!?;:'\"()")
        if not word:
            continue
        phones = g2p_word(word)
        # Check OOV
        if word.lower() not in SIMPLE_G2P:
            plan.provenance["oov_words"].append(word)

        # Syllabify
        sylls = syllabify(phones)

        # Assign stress: primary on first syllable of content words
        is_function = word.lower() in FUNCTION_WORDS
        for si, syll in enumerate(sylls):
            for phone in syll:
                if phone not in PHONE_TABLE:
                    # Unknown phone — log and skip
                    plan.provenance.setdefault("unknown_phones", []).append(phone)
                    continue
                info = PHONE_TABLE[phone]
                stress = 0
                if not is_function and si == 0 and _is_vowel(phone):
                    stress = 1
                seg = Segment(
                    i=seg_idx,
                    phone=phone,
                    kind=info["kind"],
                    t0=0.0,
                    t1=0.0,
                    word=word_idx,
                    syll=si,
                    stress=stress,
                    voiced=info["voiced"],
                )
                # Diphthong fields
                if info.get("synth") == "diphthong":
                    seg.onset = info.get("onset")
                    seg.offset = info.get("offset")
                    seg.reach = info.get("reach", 0.7)
                    # Targets from onset vowel
                    import yaml as _y
                    g = _y.safe_load(open(os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")))
                    grid = g["vowel_grid"]
                    if seg.onset in grid:
                        seg.targets = {"F1": grid[seg.onset][0], "F2": grid[seg.onset][1], "F3": grid[seg.onset][2]}
                elif info.get("synth") == "vowel":
                    import yaml as _y
                    g = _y.safe_load(open(os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")))
                    grid = g["vowel_grid"]
                    if phone in grid:
                        seg.targets = {"F1": grid[phone][0], "F2": grid[phone][1], "F3": grid[phone][2]}
                    elif phone == "ɝ":
                        seg.targets = {"F1": 450, "F2": 1500, "F3": 1800}

                plan.segments.append(seg)
                seg_idx += 1
            word_idx += 1

    # Prosody
    plan = plan_prosody(plan)

    return plan


# ── Demo ─────────────────────────────────────────────────────────────────

def demo():
    text = "This is the moon."
    plan = build_plan(text)
    print(f"Text: {text}")
    print(f"Words: {plan.words}")
    print(f"Segments: {len(plan.segments)}")
    for seg in plan.segments:
        print(f"  {seg.i}: {seg.phone:3s} kind={seg.kind:10s} t={seg.t0:.3f}-{seg.t1:.3f} stress={seg.stress} word={seg.word}")
    print(f"F0 anchors: {len(plan.f0_anchors)}")
    for a in plan.f0_anchors:
        print(f"  t={a.t:.3f} Hz={a.value:.1f} reason={a.reason}")
    print(f"Events: {len(plan.events)}")
    # JSON round-trip test
    j = plan.to_json()
    plan2 = RenderPlan.from_json(j)
    print(f"\nJSON round-trip: {'PASS' if len(plan2.segments) == len(plan.segments) else 'FAIL'}")


def main():
    parser = argparse.ArgumentParser(description="VOICE render plan")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--roundtrip", action="store_true")
    parser.add_argument("--text", type=str, default="This is the moon.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.demo or args.roundtrip:
        plan = build_plan(args.text)
        if args.json:
            print(plan.to_json())
        else:
            demo()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()