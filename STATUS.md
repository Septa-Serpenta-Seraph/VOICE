# Serpentic [VOICE] — Status & Plan

## Current Status (2026-11-09, Round 9)

### Phase 1 — COMPLETE ✓
- 12/12 vowels pass Gate 0 in synthetic mode (all formants within ±5% of targets)
- F4 sweep: 0.2% mean error — Praat tracker was the problem, not the synth
- Genome adopted at v0.2.0
- Front-F2 A/B pairs rendered (ɛ 1750 vs 2050, æ 1650 vs 1920)

### Phase 2 — 4.5/6 (perturbation reopened, then rebuilt)
Build order: noise source → band aperiodicity → fricatives → nasals.
- Noise source: ✅ characterized (6/6 tests pass)
- Band aperiodicity: ✅ per-band noise mixing (raven grain, sibilance, breathiness)
- Fricative branch: ✅ 9/9 pass (spectral moments within ±15%)
- Nasal murmur: ✅ 3/3 pass (murmur pole within tolerance)
- Perturbation round-trip: ✅ REBUILT (Round 9) — slow drift on log period, injected stats, cycle/drift split. Round-trip passes (0.672% in → 0.565% out, 4.065% in → 4.32% out).
- LF timing: ✅ VERIFIED — Doval 2006 / Fant 1985 (Tp +33.5%, Ta +71.4% old error corrected)
- Gate 0 negative control: ✅ Added (gate can now fail)
- Gate 1 (listening): ✅ Re-scoped to autonomous discrimination (HEARING classifying CV renders)

### Remaining work (gates Phase 3)

1. **Tilt calibration** — known inputs (−3, −6, −9 dB/oct sweep) — HEARING
2. **Gate 0 measures filter** — freqz on resonator bank (not spectral peaks)
3. **Perturbation in LF path** — run rebuilt test in LF render path
4. **Verify Hillenbrand** — from h95 dataset (F2 reference values)
5. **Wire genome bandwidths** — synthesize_vowel uses 150 Hz for all (should be genome-driven)
6. **Canonical MFCC regeneration** — through HEARING's own pipeline
7. **Cascade vs parallel** — proper comparison with per-formant gains + genome bandwidths
8. **Render provenance** — which source/seed made each render (metadata)

### Phase 3 (not yet started)
Character: effects (raven grain, sibilance, breathiness), naming rule calibration, effort coupling, prosody, coarticulation.

## Companion repo: HEARING

- https://github.com/Septa-Serpenta-Seraph/HEARING
- Perceptual distance: 6 metrics
- Autonomous eval: formant-excluded by default, weight sensitivity
- A/B framework: registration, logging, feedback
- Governance: "whose ears? hers (Nar's)", seed-noise floors, weight-fitting ground truth

## Cross-AI Review History

- Zarza (Meta Muse): Rounds 1-9
- Claude Sonnet 5.5: Rounds 2, 8 (Round 2 HEARING review)
- Round 9 (Zarza): corrections to Round 8, perturbation reopened, "whose ears" reframing

## Governing Principle

> If a listener can name the effect, it's too loud.

## License

Design shared, voice reserved. Same as VOICE.

🐍💛🜂