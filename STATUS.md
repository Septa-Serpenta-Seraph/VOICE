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

1. ~~**Tilt calibration**~~ ✅ DONE — true dB/octave recovers known tilts within 0.3 dB. VOICE convention is dB/decade (factor 3.01×). Canonical -4.31 = -1.43 true dB/oct. See HEARING/analysis/tilt_calibration.py.
2. ~~**Gate 0 measures filter**~~ ✅ DONE — freqz on resonator bank with genome bandwidths. All 4 formants pass (F1 0.39%, F2 0.00%, F3 0.16%, F4 0.55%). Negative control passes (wrong filter 20% off → fails). See VOICE/analysis/filter_gate0.py.
3. ~~**Perturbation in LF path**~~ ✅ DONE — both simple (0.548% jitter, 4.221% shimmer) and LF (0.453% jitter, 3.507% shimmer) pass round-trip. See VOICE/analysis/perturbation.py (--source simple/lf).
4. ~~**Verify Hillenbrand**~~ ✅ DONE — F2=1500 validated (4.7% from population median 1574.5 Hz, closest vowel /ɑ/ at 1534 Hz). F1=450 is 21.6% below median (intentional — low F1 = open quality). F3=2770 is 3.9% below median. See VOICE/analysis/hillenbrand_verify.py.
5. ~~**Wire genome bandwidths**~~ ✅ DONE — synthesize_vowel now accepts bandwidths dict (per-formant: F1=80, F2=100, F3=120, F4=150 Hz from genome). render_vowel extracts from genome filter.neutral_anchor. All 12 vowels still pass Gate 0. See VOICE/analysis/phase1_synth.py.
6. ~~**Canonical MFCC regeneration**~~ ✅ DONE — regenerated through HEARING's measure_render() over 12 synthetic vowel renders (median). New: [-237.6, -41.9, 5.3, 26.6, -59.5, 1.6, -15.9, -25.8, -14.0, -2.8, -32.1, -3.3, -4.0]. Old stale (ElevenLabs) replaced. See HEARING/analysis/regen_canonical_mfcc.py.
7. ~~**Cascade vs parallel**~~ ✅ DONE — with per-formant gains + genome bandwidths, both methods are nearly identical (parallel: 1.97% mean, cascade: 2.00% mean). Parallel wins by 0.03%. Original cascade failure (16-32% F3 error) was due to uniform bandwidth + no gains. See VOICE/analysis/cascade_vs_parallel.py.
8. ~~**Render provenance**~~ ✅ DONE — phase1_synth.py now writes provenance.json with source, seed, duration, f0, genome status/version, sample rate, bandwidths, and per-render formant values. See VOICE/analysis/phase1_synth.py and renders/phase1/provenance.json.

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