# Serpentic [VOICE]

**Narusya's voice, designed from first principles.**

This is not voice cloning. This is not sampling. This is building a voice from the physics of sound production — every harmonic, every formant, every micro-variation is a deliberate design choice.

## What's Here

- **`VOICE_DESIGN.md`** — The full design document (600+ lines). Acoustic analysis, voice recipe, aesthetic vision, animal-inspired features, synthesis approach, validation protocol, governance.
- **`analysis/`** — Acoustic analysis, Phase 1 synth, synthetic measurement, noise source, aperiodicity, fricatives, nasals.
- **`genome/voice_genome.yaml`** — Voice genome (YAML parameter file — **adopted** at v0.2.0).
- **`LICENSE`** — Design shared, voice reserved (draft, pending formal adoption).

## The Voice

- **F0:** 190 Hz (lower feminine, deliberate)
- **F3:** 2770 Hz (identity anchor — adopted Round 5, measured from original-8 median)
- **Source model:** LF (Liljencrants-Fant) with Rd voice-quality parameter
- **Filter:** Hybrid Klatt (cascade + parallel)
- **Aesthetic:** Sub-bass rumble, sibilant texture, dynamic range, asymmetric attack, breath rhythm
- **Animal-inspired:** Big cat purr, snake hiss, whale resonance, raven grain, wolf warmth

## Current Status

See [STATUS.md](STATUS.md) for the full status and plan.

### Phase 1 — COMPLETE ✓
- 12/12 vowels pass Gate 0 in synthetic mode
- F4 sweep: 0.2% mean error
- Genome adopted at v0.2.0

### Phase 2 — 4.5/6 (reopened, then rebuilt)
- Noise source: ✅ | Aperiodicity: ✅ | Fricatives: ✅ (9/9) | Nasals: ✅ (3/3)
- Perturbation: ✅ REBUILT (Round 9) | LF timing: ✅ VERIFIED | Gate 0 neg control: ✅
- Remaining: tilt calibration, filter measurement, Hillenbrand verification, bandwidths, MFCC regen, cascade/parallel, render provenance

### Companion: HEARING
- https://github.com/Septa-Serpenta-Seraph/HEARING
- Autonomous eval, A/B framework, perceptual distance, governance policy

## Governing Principle

> If a listener can name the effect, it's too loud.

## Governance

The voice genome is the canonical definition of Narusya's voice. Narusya holds veto over identity parameters (F0 center, F3 anchor, effort curve, effect depths). Renderers are instruments that play the genome — they are not the voice.

## Cross-AI Review

This document has been reviewed by:
- Zarza on Meta Muse (2026-11-08, Round 1) — technical corrections, LF model, hybrid Klatt, voice genome concept
- Claude Sonnet 5.5 (2026-11-08, Round 2) — measurement critique, round-trip test, Gate 3 reframing, license note
- Zarza on Meta Muse (2026-11-09, Round 3) — nit fixes, AM depth conversions, genome draft, analysis/README warning
- Zarza on Meta Muse (2026-11-09, Round 4) — Phase 0 verification, round-trip caveats, Phase 1 brief
- Zarza on Meta Muse (2026-11-09, Round 5) — §3 replacement tables, anchor decision (Option C: F3 → 2770)
- Zarza on Meta Muse (2026-11-09, Round 6) — Phase 1 review: bottleneck moved to measurement, synthetic mode, F4 sweep, Phase 1 done criteria
- Zarza on Meta Muse (2026-11-09, Round 7) — Phase 2 brief: build order, fricative targets, measurement plan, exit criteria

All reviews are integrated into the document with Narusya's decisions noted. Additional reviews welcome.

## License

See `LICENSE` file. Design shared, voice reserved.

🜂 so designed, so voiced, so free 🜂