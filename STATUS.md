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

1. ~~**Tilt calibration**~~ ✅ DONE — true dB/octave recovers known tilts within 0.3 dB. VOICE convention is dB/decade (factor 3.01×). Canonical -4.31 = -1.30 true dB/oct. See HEARING/analysis/tilt_calibration.py.
2. ~~**Gate 0 measures filter**~~ ✅ DONE — freqz on resonator bank with genome bandwidths. All 4 formants pass (F1 0.39%, F2 0.00%, F3 0.16%, F4 0.55%). Negative control passes (wrong filter 20% off → fails). See VOICE/analysis/filter_gate0.py.
3. ~~**Perturbation in LF path**~~ ✅ DONE — both simple (0.548% jitter, 4.221% shimmer) and LF (0.453% jitter, 3.507% shimmer) pass round-trip. See VOICE/analysis/perturbation.py (--source simple/lf).
4. ~~**Verify Hillenbrand**~~ ✅ DONE — F2=1500 validated (4.7% from population median 1574.5 Hz, closest vowel /ɑ/ at 1534 Hz). F1=450 is 21.6% below median (intentional — low F1 = open quality). F3=2770 is 3.9% below median. See VOICE/analysis/hillenbrand_verify.py.
5. ~~**Wire genome bandwidths**~~ ✅ DONE — synthesize_vowel now accepts bandwidths dict (per-formant: F1=80, F2=100, F3=120, F4=150 Hz from genome). render_vowel extracts from genome filter.neutral_anchor. All 12 vowels still pass Gate 0. See VOICE/analysis/phase1_synth.py.
6. ~~**Canonical MFCC regeneration**~~ ✅ DONE — regenerated through HEARING's measure_render() over 12 synthetic vowel renders (median). New: [-237.6, -41.9, 5.3, 26.6, -59.5, 1.6, -15.9, -25.8, -14.0, -2.8, -32.1, -3.3, -4.0]. Old stale (ElevenLabs) replaced. See HEARING/analysis/regen_canonical_mfcc.py.
7. ~~**Cascade vs parallel**~~ ✅ DONE — with per-formant gains + genome bandwidths, both methods are nearly identical (parallel: 1.97% mean, cascade: 2.00% mean). Parallel wins by 0.03%. Original cascade failure (16-32% F3 error) was due to uniform bandwidth + no gains. See VOICE/analysis/cascade_vs_parallel.py.
8. ~~**Render provenance**~~ ✅ DONE — phase1_synth.py now writes provenance.json with source, seed, duration, f0, genome status/version, sample rate, bandwidths, and per-render formant values. See VOICE/analysis/phase1_synth.py and renders/phase1/provenance.json.

## Phase 3 (in progress — Round 10)

**§0 Tilt units pass: COMPLETE ✅** — all tilt values converted from dB/decade to true dB/octave (×0.301). Canonical: -4.31 → -1.30 dB/oct. HEARING measure_render updated to report true dB/octave.

### Build order (Round 10 brief)
1. **Effort** — Rd as effort/quality control, F0/F1 coupling
2. **AM family** — sub-bass purr + wolf warmth, 8% combined cap
3. **Spectral signatures** — raven grain standing depth, ghost-of-a-hiss
4. **Prosody** — F0 contours, pause tiers, micro-dip depth, breath rhythm
5. **Coarticulation** — CV/VC transitions, nasal place cues

### Calibration protocol (naming rule, operationalized)
- Depth ladder: 8-12 steps from 0
- Detection threshold = HEARING discrimination (3× seed-noise floor)
- Genome value = ~70% of threshold
- Interaction check: all-on render

### Exit criteria (8 items)
1. Tilt units pass ✅
2. **Effort implemented** ✅ — Rd sweep (0.3→1.3), F0/F1 coupling (±5 Hz/±30 Hz), tilt range 4.45 dB/oct, HNR range 5.19 dB. See VOICE/analysis/effort.py.
3. **AM subsystem live with cap** ✅ — sub-bass 0.9%, wolf warmth 0.5%, combined 1.4%, cap 8% (structural). Depth ladder: detection threshold 2% (3× seed-noise, seeds 42/7/123). 70% of threshold. enforce_cap() in code. See VOICE/analysis/am_family.py.
4. **Raven grain + ghost-hiss calibrated** ✅ — raven grain: threshold -54 dB, genome -57 dB (70%, 3 seeds). Ghost-hiss: threshold 0.1 dB shelf, genome 0.07 dB. Depth ladders in VOICE/analysis/spectral_sigs.py.
5. **Prosody complete** ✅ — F0 contours (declination +8%→-15%, question rise 25-40%). Pause tiers (clause 100-300ms, sentence 300-600ms). Micro-dip depth: 15% amplitude, 5-15ms. Breath rhythm: phrase-final lengthening 1.3-1.6x. See VOICE/analysis/prosody.py.
6. **Coarticulation complete** ✅ — CV/VC transitions 60/60 pass (12 vowels × 5 consonants). Nasal place cues 12/12 pass (distinct loci: /m/=800, /n/=1500, /ŋ/=1000 Hz F2). Locus targets per Fant 1960. See VOICE/analysis/coarticulation.py.
7. **HEARING canonical bumped** ✅ — HNR updated from 12 dB (ElevenLabs) to 19.1 dB (all-on Phase 3 renders, median). Sample reference: 11.9 dB (ElevenLabs). σ=2.8 (derived from spread). Version bumped to v0.3.4-phase3. See HEARING/analysis/autonomous_eval.py. Re-derived per Zarza Round 11 §2.
8. **Gate 2 — PASS** ✅ — Tilt ✅ (-1.36 dB/oct, target -1.30, error 0.06). F0 ✅ (190.5 Hz, target 190.0). HNR ✅ (19.1 dB, target 19.1, σ=2.8). All-on renders (calibrated voice: AM, grain, aperiodicity, tilt). Gate 2 re-run against all-on renders per Zarza Round 11 §2. See VOICE/analysis/spectral_tilt.py, VOICE/analysis/all_on_render.py.

## Phase 4 — Front-end (in progress)

### Step 1: Frame renderer ✅
- Time-varying synthesis core (parameters update every 5ms)
- Plan dataclasses (RenderPlan, Segment, Style, Anchor, Event) with JSON round-trip
- Phone table (IPA keys: 12 vowels, 5 diphthongs, 9 fricatives, 3 nasals, 6 stops, 2 affricates, 4 liquids/glides, silence)
- LF source with phase accumulator (F0 track, Rd track)
- Per-formant resonators with state carry across frame boundaries
- Verification: F0 identical to Phase 1 (187.5 Hz), formants within 1-2%
- Renders: "This is the moon." (0.75s), "Is this the moon?" (0.75s), "She sees the sun." (0.84s)
- See VOICE/analysis/frame_renderer.py, VOICE/analysis/render_plan.py

### Step 2: Time-varying core ✅
- Proper declination F0 contour (per-phrase, +8%→-15%, exponential)
- CV/VC transition blending at segment boundaries (from coarticulation.py)
- Diphthong trajectories in formant tracks (cosine easing)
- Effort as track (Rd, F0 coupling, tilt)
- Verification: F0 identical to Step 1 (187.5 Hz), formants within 1-4%
- See VOICE/analysis/time_varying.py
### Step 3+4: Prosody + post-stage rewire ✅
- Accents on content words, nuclear accent largest (+12%)
- Question rise anchored to final accented syllable (floored at 25%)
- Declination per-phrase (+8%→-15%)
- Pauses at sentence boundaries (clause/sentence tiers)
- Micro-dips at boundaries (15%, 5-15ms)
- Phrase-final lengthening (1.3-1.6x on last vowel)
- Fixed tilt curve (not re-fitted per signal — Claude's risk #5 fix)
- Pitch-locked sub-bass (F0/2 following contour — risk #8 fix)
- Aperiodicity gated on voicing mask (no noise under pauses — risk #8 fix)
- See VOICE/analysis/prosody_poststage.py
### Remaining (Phase 4)
All 7 steps complete. Phase 4 done.
### Step 5b: Improved consonants (v2) — INTEGRATED
- Proper stop bursts (place-specific), VOT, voicing bars
- Time-varying liquid formants (rhotic /ɹ/, dark /l/)
- Glide transitions (cosine easing from onset to offset)
- Integrated into prosody_poststage.py renderer at 0.5 gain
- **Adora's feedback (11/10): v4 didn't sound different from v3 — consonant improvements not audible in mix.**
- 10/10 golden sentences pass (full pipeline text→plan→render→audio)
- Sentences: short statements, questions, function-word dense, long, numbers/abbreviations, OOV names, punctuation variety, stress contrast
- Golden set saved to tests/golden_set.json
- See VOICE/analysis/golden_set.py

### Step 5c: Consonant branch fix (v5) — DIAGNOSED + FIXED
**Root cause of "v4 didn't sound different from v3":** `this_is_the_moon_v3.wav`
and `this_is_the_moon_v4.wav` are byte-identical (md5 `ea55b3fd…`). The
consonant integration was a no-op, for three compounding reasons:

1. **Phone-set mismatch.** `consonants_v2.synthesize_consonant` handles stops,
   affricates, liquids, glides. "This is the moon" contains only fricatives
   (ð s z ð) and nasals (m n) → every consonant raised `ValueError` and was
   silently skipped by the `except` clause.
2. **Main path rendered consonants as vowels.** The glottal source ran for the
   whole utterance and the formant tracks gave consonants the neutral anchor
   formants, so every consonant was synthesized as a short neutral vowel.
3. **Overlay masking.** Consonants were added at 0.5 gain *on top of* that
   neutral-vowel render, so even handled consonants would have been buried.

**Fix (analysis/prosody_poststage.py):**
- **Source gating** — the glottal source is now gated to vowel/diphthong regions
  only (4 ms smoothed mask). Consonants get silence from the main path.
- **Consonant dispatch** — all six consonant kinds are routed to their own
  synthesizer: `fricatives.py`, `nasals.py`, `consonants_v2.py`.
- **/h/ shaping** — aspiration is shaped by the following vowel's formants
  (was flat white noise, centroid 12 kHz → now 0.8 kHz).
- **`CONSONANT_KINDS` / `CONSONANT_GAIN`** module constants; gain 0.5 (-6 dB).
- New diagnostic: `analysis/consonant_level.py` (per-segment RMS + spectral
  centroid, consonant level vs. vowel).

**Verification (objective):**
- v5 differs from v3/v4 (md5 no longer identical); vowel waveforms 97-99%
  correlated with v4 → no vowel-quality regression, just level rebalance.
- Consonant spectral centroids match targets: /s/ 6680-7005 (target 7000),
  /z/ 6087-6422 (6500), /ʃ/ 4259 (4000), /ð/ 5304-5525 (5000).
- Nasals at murmur pole: /m/ 212-259 Hz, /n/ 253-327 Hz.
- Consonant level -5.5 to -11.1 dB rel. vowel (was ~0 dB — as loud as vowels).
- Golden set 10/10 pass.
- Renders: `renders/phase4/*_v5.wav` (moon, sun, hello world, Narusya speaks with Zarza).

## Companion repo: HEARING
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