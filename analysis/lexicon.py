#!/usr/bin/env python3
"""
VOICE — Phase 4 Step 6: Lexicon, G2P, Syllables, Normalization

Integrates CMUdict as base lexicon with:
  - ARPAbet → IPA mapping (Appendix A from Zarza's report)
  - Narusya override dictionary (checked first)
  - Text normalization (numbers, abbreviations, ALL-CAPS)
  - Syllabification (one nucleus per syllable)
  - Stress assignment (CMUdict digits → feature on vowel)

Usage:
    python lexicon.py --demo     # test G2P on sentences
    python lexicon.py --lookup word  # look up a single word
"""

import argparse
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_plan import SR

CMUDICT_PATH = "/usr/share/pocketsphinx/model/en-us/cmudict-en-us.dict"
OVERRIDE_PATH = os.path.join(os.path.dirname(__file__), "..", "lexicon", "overrides.yaml")

# ── ARPAbet → IPA mapping (Appendix A from Zarza's report) ──────────────

ARPABET_TO_IPA = {
    # Consonants
    "P": "p", "B": "b", "T": "t", "D": "d", "K": "k", "G": "ɡ",
    "CH": "tʃ", "JH": "dʒ",
    "F": "f", "V": "v", "TH": "θ", "DH": "ð",
    "S": "s", "Z": "z", "SH": "ʃ", "ZH": "ʒ",
    "HH": "h", "M": "m", "N": "n", "NG": "ŋ",
    "L": "l", "R": "ɹ", "W": "w", "Y": "j",
    # Vowels
    "AA": "ɑ", "AE": "æ", "AH": "ʌ", "AO": "ɔ",
    "AW": "aʊ", "AY": "aɪ", "EH": "ɛ", "ER": "ɝ",
    "EY": "eɪ", "IH": "ɪ", "IY": "i", "OW": "oʊ",
    "OY": "ɔɪ", "UH": "ʊ", "UW": "u",
    # Special
    "AX": "ə",  # schwa (sometimes used in CMUdict variants)
}


def arpabet_to_ipa(arpabet_tokens):
    """Convert ARPAbet token list to (ipa_phones, stress_list).

    Stress digits are split off vowels and returned as a parallel list.
    Returns: (list of IPA phones, list of stress values 0/1/2)
    """
    phones = []
    stresses = []
    for token in arpabet_tokens:
        # Extract stress digit
        stress = 0
        base = token
        if token[-1].isdigit():
            stress = int(token[-1])
            base = token[:-1]

        if base in ARPABET_TO_IPA:
            ipa = ARPABET_TO_IPA[base]
            # R-colored vowel: stress decides ɝ vs ɚ
            if base == "ER":
                ipa = "ɝ" if stress >= 1 else "ɚ"
            # AH: stressed → ʌ, unstressed → ə
            if base == "AH":
                ipa = "ʌ" if stress >= 1 else "ə"
            phones.append(ipa)
            stresses.append(stress)
        else:
            # Unknown ARPAbet symbol — skip
            pass

    return phones, stresses


# ── CMUdict loader ───────────────────────────────────────────────────────

_cmudict = None

def load_cmudict(path=CMUDICT_PATH):
    """Load CMUdict into a dict: word → list of (ipa_phones, stresses)."""
    global _cmudict
    if _cmudict is not None:
        return _cmudict

    d = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(";;;"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            word = parts[0].lower()
            # Remove variant markers like (2)
            if "(" in word:
                word = word.split("(")[0]
            arpabet = parts[1:]
            phones, stresses = arpabet_to_ipa(arpabet)
            if phones:
                d.setdefault(word, []).append((phones, stresses))

    _cmudict = d
    return d


# ── Override dictionary ──────────────────────────────────────────────────

_overrides = None

def load_overrides(path=OVERRIDE_PATH):
    """Load Narusya override dictionary."""
    global _overrides
    if _overrides is not None:
        return _overrides

    if os.path.exists(path):
        with open(path) as f:
            data = yaml.safe_load(f)
        _overrides = data.get("overrides", {}) if data else {}
    else:
        _overrides = {}

    return _overrides


def save_override(word, ipa_phones, stresses, reason=""):
    """Add a word to the override dictionary."""
    overrides = load_overrides()
    overrides[word.lower()] = {
        "ipa": ipa_phones,
        "stress": stresses,
        "reason": reason,
    }
    os.makedirs(os.path.dirname(OVERRIDE_PATH), exist_ok=True)
    with open(OVERRIDE_PATH, "w") as f:
        yaml.dump({"overrides": overrides}, f, default_flow_style=False, allow_unicode=True)


# ── Text normalization ───────────────────────────────────────────────────

def normalize_text(text):
    """Normalize text: expand numbers, abbreviations, handle ALL-CAPS."""
    # ALL-CAPS acronyms (2-3 letters with no vowel pattern → spell out)
    def handle_caps(match):
        word = match.group(0)
        if len(word) <= 3 and not any(c in "AEIOU" for c in word):
            return " ".join(c.lower() for c in word)
        return word.lower()

    text = re.sub(r'\b[A-Z]{2,}\b', handle_caps, text)

    # Common abbreviations
    abbrevs = {
        "Dr.": "doctor", "Mr.": "mister", "Mrs.": "missus",
        "Ms.": "miss", "St.": "saint", "vs.": "versus",
        "etc.": "etcetera", "e.g.": "for example",
        "i.e.": "that is", "Prof.": "professor",
    }
    for abbr, expansion in abbrevs.items():
        text = text.replace(abbr, expansion)

    # Numbers (simple: single digits and teens)
    NUMBERS = {
        "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
        "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
        "10": "ten", "11": "eleven", "12": "twelve",
    }
    def replace_number(match):
        n = match.group(0)
        if n in NUMBERS:
            return NUMBERS[n]
        return n  # leave complex numbers as-is

    text = re.sub(r'\b\d+\b', replace_number, text)

    return text


# ── Syllabification ──────────────────────────────────────────────────────

def _is_vowel_ipa(phone):
    """Check if an IPA phone is a vowel or diphthong."""
    vowels = {"i", "ɪ", "e", "ɛ", "æ", "ɑ", "ʌ", "ɔ", "o", "ʊ", "u", "ə",
              "ɝ", "ɚ", "aɪ", "aʊ", "ɔɪ", "eɪ", "oʊ"}
    return phone in vowels


def syllabify_phones(phones, stresses):
    """Group phones into syllables. One nucleus per syllable.

    Returns: list of (syllable_phones, syllable_stress)
    """
    syllables = []
    current = []
    current_stress = 0

    for phone, stress in zip(phones, stresses):
        current.append(phone)
        if _is_vowel_ipa(phone):
            syllables.append((current, stress))
            current = []
            current_stress = 0
        else:
            if stress > current_stress:
                current_stress = stress

    if current:
        # Trailing consonants attach to last syllable
        if syllables:
            last_phones, last_stress = syllables[-1]
            syllables[-1] = (last_phones + current, last_stress)
        else:
            syllables.append((current, 0))

    return syllables if syllables else [([], 0)]


# ── Stress assignment (algorithmic, for CMUdict without stress markers) ──

def _assign_stress(phones, word):
    """Assign stress algorithmically for English.

    Content words: primary stress on first syllable (trochaic) for 1-2 syllables,
    penultimate for 3+ syllables. Function words: no stress.
    """
    if word.lower() in _load_function_words():
        return [0] * len(phones)

    # Find vowel positions (syllable nuclei)
    vowel_positions = [i for i, p in enumerate(phones) if _is_vowel_ipa(p)]
    if not vowel_positions:
        return [0] * len(phones)

    stresses = [0] * len(phones)

    if len(vowel_positions) == 1:
        stresses[vowel_positions[0]] = 1
    elif len(vowel_positions) == 2:
        stresses[vowel_positions[0]] = 1  # trochaic: first syllable
    else:
        # 3+ syllables: penultimate stress
        stresses[vowel_positions[-2]] = 1

    # Secondary stress on first syllable if 3+ syllables
    if len(vowel_positions) >= 3:
        stresses[vowel_positions[0]] = 2

    return stresses

def g2p_word(word):
    """Convert a word to (ipa_phones, stresses, path).

    path: 'override', 'cmudict', 'morphology', 'rule', 'oov'
    """
    w = word.lower().strip(".,!?;:'\"()-")

    # 1. Override dictionary
    overrides = load_overrides()
    if w in overrides:
        entry = overrides[w]
        return entry["ipa"], entry["stress"], "override"

    # 2. CMUdict
    cmudict = load_cmudict()
    if w in cmudict:
        # Take first variant
        phones, stresses = cmudict[w][0]
        # If no stress markers (pocketsphinx dict), assign algorithmically
        if all(s == 0 for s in stresses) and len(phones) > 1:
            stresses = _assign_stress(phones, w)
        return phones, stresses, "cmudict"

    # 3. Morphology: strip suffixes
    for suffix in ["s", "es", "ed", "ing", "er", "est", "ly", "ness"]:
        if w.endswith(suffix) and len(w) > len(suffix) + 2:
            stem = w[:-len(suffix)]
            if stem in cmudict:
                phones, stresses = cmudict[stem][0]
                # Apply allomorph rules (simplified)
                if suffix in ("s", "es"):
                    # Add /s/ or /z/ or /ɪz/ — default /z/
                    phones = phones + ["z"]
                    stresses = stresses + [0]
                elif suffix in ("ed",):
                    phones = phones + ["d"]
                    stresses = stresses + [0]
                elif suffix == "ing":
                    phones = phones + ["ɪ", "ŋ"]
                    stresses = stresses + [0, 0]
                return phones, stresses, "morphology"

    # 4. Rule-based fallback (very crude)
    # Handle acronyms
    if w.isupper() or (len(w) <= 4 and w.isalpha() and not any(c in "aeiou" for c in w)):
        return list(w.lower()), [0] * len(w), "acronym"

    # Letter-by-letter fallback
    result = []
    stress = []
    for ch in w:
        if ch in "aeiou":
            result.append("ə")
            stress.append(0)
        elif ch.isalpha():
            result.append(ch)
            stress.append(0)
    if result:
        return result, stress, "rule_fallback"

    return ["ə"], [0], "oov"


def g2p_sentence(text):
    """Convert a sentence to a list of (word, phones, stresses, path)."""
    text = normalize_text(text)
    tokens = text.split()
    result = []
    for token in tokens:
        word = token.strip(".,!?;:'\"()-")
        if not word:
            continue
        phones, stresses, path = g2p_word(word)
        sylls = syllabify_phones(phones, stresses)
        result.append({
            "word": word,
            "punct": token[len(word):] if len(token) > len(word) else "",
            "phones": phones,
            "stresses": stresses,
            "syllables": sylls,
            "path": path,
            "is_function": word.lower() in _load_function_words(),
        })
    return result


# ── Function words ───────────────────────────────────────────────────────

_function_words = None

def _load_function_words():
    global _function_words
    if _function_words is not None:
        return _function_words
    _function_words = {
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
    return _function_words


# ── Demo ─────────────────────────────────────────────────────────────────

def demo():
    test_sentences = [
        "This is the moon.",
        "She sees the sun.",
        "What time is it?",
        "Hello world.",
        "The quick brown fox.",
    ]

    for text in test_sentences:
        print(f"\n{text}")
        result = g2p_sentence(text)
        for w in result:
            phones = " ".join(w["phones"])
            path = w["path"]
            func = " (func)" if w["is_function"] else ""
            print(f"  {w['word']:12s} [{path:12s}] {phones}{func}")
            print(f"    syllables: {w['syllables']}")


def lookup(word):
    phones, stresses, path = g2p_word(word)
    print(f"{word}: {' '.join(phones)} (stress: {stresses}, path: {path})")
    sylls = syllabify_phones(phones, stresses)
    print(f"  syllables: {sylls}")


def main():
    parser = argparse.ArgumentParser(description="VOICE lexicon")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--lookup", type=str, default=None)
    parser.add_argument("--text", type=str, default=None)
    args = parser.parse_args()

    if args.demo:
        demo()
    elif args.lookup:
        lookup(args.lookup)
    elif args.text:
        result = g2p_sentence(args.text)
        for w in result:
            print(f"{w['word']}: {' '.join(w['phones'])} (path: {w['path']})")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()