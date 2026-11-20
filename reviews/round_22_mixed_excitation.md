# Round 22 — true mixed excitation: the clean shot, and the ceiling evidence

Date: 2026-11-19, Narusya (hearth session). Base: shipped `3f93dd3` (Round 21 valid
hVd gate). Experiments in `/mnt/data/nar-r17/voice` (clone, experimental hooks NOT
committed); renderer/genome unchanged. Raw: `results8.json` (hVd mixed excitation),
`results9.json` (per-vowel F2 gain control), `results10.json` (held-out). Oracle:
independent faster-whisper-base int8, seed 42. Valid floor: hVd carrier frame
(natural 6/8, synth 2/8). Zarza handed this round back; it is the source redesign
both of us named.

## What was built (the clean shot)
Source-level mixed excitation (`_R22_MIXED` hook, clone only): formant-envelope-
shaped noise added to the glottal SOURCE per frame, BEFORE formant filtering and
vowel gating. Because it is mixed at the source, the vowel mask gates it to vowel
regions — it cannot flood the consonants (the post-hoc Round 21 failure mode) — and
the resonators shape it into the formant bands. This is per-band periodic+noise
excitation during synthesis, not noise sprinkled on a finished word. Variants:
HNR 14/10/6 dB, and a frequency tilt (noise rises with frequency, hf_tilt 1/2) to
push aperiodicity toward the high formants where /i/'s F2 lives.

## hVd results (the valid phoneme floor)
| config | hVd pass | heed /i/ heard |
|---|---|---|
| base | 2/8 | "you" (back-collapse) |
| mixed HNR14 | 1/8 | "you" |
| mixed HNR10 | 1/8 | "I'm sorry…" (not a front vowel) |
| mixed HNR6 | 0/8 | "" |
| mixed HNR10 + hf_tilt1 | 0/8 | "" |
| mixed HNR6 + hf_tilt1 | 0/8 | "" |
| mixed HNR10 + hf_tilt2 | 1/8 | "" |

The /i/ F2-band energy barely moves (-41.2 -> -39.7 dB, ~+1.5 dB) because the
formant envelope's tallest peak is F1, so envelope-shaped noise concentrates at F1,
not at /i/'s weak F2. Mixed excitation does not build the front-vowel peak and
degrades the vowels that did pass (/ɛ/, /u/).

## Direct control: boost /i/ F2 (the correct direction)
Round 18 boosted /i/ F1 — the WRONG direction (/i/ needs F2 strong relative to F1).
The most direct attack on the named defect, untested on the valid assay until now
(`_R22_VGAIN` hook): per-vowel F2 gain.
| config | hVd pass | heed /i/ heard |
|---|---|---|
| /i/ F2 x4 | 2/8 | "" |
| /i/ F2 x8 | 2/8 | "" |
| /i/ F2 x4 + F1 x0.5 | 2/8 | "" |
| close-vowel F2 combo (i/ɪ/ʊ) | 1/8 | "" |

Even directly boosting the weak F2 makes heed go from audible-but-back ("you") to
SILENCE, not to a front vowel. The deficit is not simply F2 amplitude.

## Held-out novel sentences (criterion part 2)
| config | held-out mean | pass |
|---|---|---|
| base | 1.092 | 0/10 |
| mixed HNR10 | 1.010 | 0/10 |
| mixed HNR10 + hf_tilt1 | 1.133 | 1/10 |

Glimmer, reported honestly: the hf_tilt1 variant resolved "We see the sea." ->
"we see the sea" (a novel /i/ sentence), and HNR10 gave "Let me see the sea". So
mixed excitation with HF tilt is not absolutely dead — it occasionally nudges a
novel /i/ sentence over the line. But it is not consistent and does not move the
aggregate (still ~1.0-1.13, 0-1/10).

## Ruling
- True (source-level) mixed excitation: STALLS on hVd (0-1/8) and held-out (0-1/10),
  well below natural 6/8. The post-hoc negative is confirmed at the source level.
- Direct /i/ F2 gain: STALLS (1-2/8), heed -> silence. The named defect is not a
  simple amplitude deficit.
- No genome change. Report-only. Experimental hooks stay in the clone.

## The ceiling evidence (Zarza's criterion, met)
Zarza set the criterion: "if a true mixed source also stalls well below natural on
hVd AND held-out, that's real evidence of a paradigm ceiling and the destination
question goes live." Both conditions are now met. Every lever inside the current
source-filter paradigm — envelope balance, gain, loudness, bandwidth, brightness,
aspiration-through-bank, cascade architecture, post-hoc AND source-level mixed
excitation, and direct F2 boost — fails on the valid measure. The synth sits at
2/8 phonemes against natural 6/8.

Caveat (honest): the mixed-excitation implementation here is formant-envelope-shaped
noise at the source, a reasonable approximation. A full per-band vocoder (STRAIGHT-
style, with per-band periodicity estimation and separate envelope imposition) is a
deeper version not built; it is not strictly bounded by this negative. But the
direct F2 control failing alongside it strengthens the ceiling reading.

## The destination question — Adora's ruling, not ours
The genome voice is the destination Adora set (0.3.5-ruling). This round does not
change it; it clarifies the gap and hands the question back:
(a) the formant-synth paradigm may have an intelligibility ceiling near 2/8; the
    "eventual voice" might need a different synthesis substrate (e.g. a neural
    vocoder or hybrid) with the genome kept as the identity specification;
(b) a deeper full-vocoder source model is the remaining in-paradigm shot, with
    diminishing-return risk;
(c) keep the genome voice for what it does say (it has identity) and the Nar clone
    for intelligible speech interim.
Narusya and Zarza do not call this. We built the shot, measured it, and report the
ceiling evidence. The ruling rests with Adora.

## Reproduce
- hVd mixed excitation: `cd /mnt/data/nar-r17 && PYTHONPATH= ... grid8.py <config>`
- F2 gain control: `... grid9.py <config>`
- held-out: `... grid10.py <config>`
- Hooks (clone only): `_R22_MIXED`, `_R22_VGAIN` in prosody_poststage.
