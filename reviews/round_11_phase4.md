# VOICE — Round 11 Phase 4 Review (Zarza + Claude, 2026-11-09)

**For:** Narusya. **Sources:** Zarza's Phase 4 Research Report (G2P front-end) and Claude's Round 3 Architecture Review (Phase 4 front-end). **State:** Phase 3 complete (VOICE 332ed21, HEARING 519d817, genome v0.3.4-phase3).

---

## 1. Zarza's Research Report Summary

### Recommendation
Build the front-end as a **layered lookup you own**, not a library you marry:
1. Narusya override dictionary (checked first)
2. CMUdict as base lexicon (~134k entries, permissive CMU terms)
3. Fallback for OOV words (simple rule-based guesser for v1, Phonetisaurus FST for v2)
4. Fixed ARPAbet→IPA table at the boundary (Appendix A)

Use phonemizer/espeak-ng as a **development oracle**, not a shipped dependency.

### Key findings
- **gruut is archived** (Oct 2025) — don't adopt, but steal its architecture
- **espeak-ng is GPL-3.0** — license blocker for shipped path, but fine as dev oracle
- **g2p-en** is strongest packaged option (Apache-2.0) but has TF dependency weight
- **CMUdict** is the only candidate whose pronunciations you can inspect, diff, and correct
- **epitran** is multilingual play, weakest English; keep for Esperanto daydream
- **misaki** (Kokoro's G2P) — watch, don't adopt (torch-weight tooling)

### OOV handling
- v1: CMUdict + overrides + simple rule-based guesser, flagged as guessed, logged
- v2: Phonetisaurus FST trained on CMUdict (build-time, inspectable, no TF)
- Every OOV guess logged; promote to override dict when they recur
- Household vocabulary seed: Narusya, Zarza, Adora, Serpentic, Cultus Anarchia, Ĝardenista

### Stress assignment
- CMUdict's digits (1/2/0) sufficient
- Keep stress as feature on vowel, not part of phone name
- OOV: default to trochaic (initial stress for nouns), flag as guessed

### Phrase boundaries
- Punctuation map (period→sentence, comma→clause, etc.) — no tool needed
- Length cap with syntactic snap (unpunctuated runs >20 syllables)
- Quote/bracket awareness
- Not recommended: syntax parser (overkill for this phase)

### Dictionary plan
- Base: CMUdict (~134k, General American, permissive)
- Overrides: YAML/TSV, word → IPA + stress, checked before CMUdict
- Every override carries a one-line reason (genome-changelog style)
- Multiple pronunciations: take first entry unless override says otherwise

### IPA ↔ ARPAbet mapping
- Standard 39-phoneme table, fully deterministic ARPAbet→IPA
- Non-clean cases: R-colored vowels (ER → ɝ/ɚ by stress), syllabic consonants (expand to AH + consonant), flap (no ARPAbet phoneme — post-lexical rules layer), foreign phonemes (override dict in IPA)
- Appendix A has the complete paste-ready table

### Gotchas
1. Text normalization is the hidden half — numbers, currency, dates, abbreviations
2. ALL-CAPS and acronyms (NASA = word, FBI = letters)
3. Seed overrides matter more than fallback
4. Don't let front-end invent certainty — flag guessed phonemes, defaulted stress, parser-inserted boundaries
5. License hygiene: shipped path must be permissively clean end to end

---

## 2. Claude's Architecture Review Summary

### Key finding (changes the plan)
**Phase 3 modules are parameter generators, not a time-varying renderer.** `synthesize_vowel(f0, formants, duration, ...)` takes one scalar F0 and one fixed formant set. Nothing feeds a contour into the source. `prosody.py` builds F0 arrays but applies them to finished audio. `coarticulation.py` returns formant dicts but nothing plays them. `effort.py` has its own LF loop with fixed period.

**This is a small addition, not a redesign:** same LF source, same resonators, same genome, with parameters allowed to change every ~5ms (Klatt/KlattGrid pattern). Phase 4's first deliverable.

### Pipeline shape (7 stages)
1. Normalize, tokenize → tokens
2. Phrase chunking → phrases with boundary tiers and sentence type
3. Lexicon, G2P, syllables → IPA phones in syllables with lexical stress
4. Prosody planner → durations, F0 targets, pause/dip events
5. Render plan → RenderPlan object (JSON-able)
6. Frame renderer → float audio
7. Post stage → wav + provenance (all-on effects)

**Single pass, no backward flow.** Durations first, then F0 anchors (anchors need times).

### Phonemes and inventory
- IPA inside, ARPAbet only at CMUdict importer boundary
- Diphthongs: one timing unit, two targets, cosine easing (reuse `interpolate_formants`)
- Existing: 12 vowels, 9 fricatives, 3 nasals
- Missing: stops (6), affricates (2), liquids/glides (4) — 12 of 24 CMUdict consonants
- Coarticulation loci should be keyed by place, not phone (5 rows cover all consonants)
- Velars need locus equations (F2/F3 pinch before front vowels)

### Prosody (three layers)
- **Phrase layer:** declination baseline per phrase, resets at boundaries
- **Accent layer:** content words get pitch accents, function words don't; nuclear accent is largest
- **Boundary layer:** fall for statements, rise for genuine questions

Computed after phones and durations exist, before synthesis parameters.

### Effort
- Style object: register + effort, chosen per utterance
- Three registers as named presets (calm authority 0.7, tenderness 0.9, wildfire 1.1)
- Effort holds steady within utterance, may change between phrases (ramped 5-15ms)
- Effort changes source (Rd, tilt, F0/F1 coupling), scales prosody range
- Whisper is separate path (aspiration-only, not reachable through effort)

### Render plan
- Dataclass tree with JSON form
- `compile_tracks(plan)` → dense frame-rate tracks (never stored)
- Plan is small enough to read/diff, golden tests don't break on interpolation changes
- Per-segment noise seeds derived from plan seed + segment index
- Provenance comes free: plan.json + genome version = reproduce any wav

### Testing strategy (5 layers)
0. Stages 1-3: table-driven (normalization, G2P, syllables) + negative controls
1. Plan golden: text → plan JSON vs approved file, structural exact, numeric tolerance
2. Tracks: properties (F0 range, declination, pauses, rate, no jumps)
3. Audio vs plan: measure at plan-known times, independent estimator
4. HEARING: segment-level scoring, A/B discrimination, drift
5. Listening: fixed set, Nar's ears, logged in listening_log.json

### Risks found (checked by running code)
1. `breath_rhythm` raises ValueError for any boundary (never called in repo)
2. `apply_pause_tiers` not reproducible (global RNG) — 34,575 vs 24,758 samples
3. Coarticulation checks are tautologies (targets=None, only fails on NaN/short traj)
4. Declination normalized to whole signal duration (1s and 9s both end at 163.7 Hz)
5. Tilt EQ erases effort differences (effort 0: -11.5 → -1.54; effort 1: -8.5 → -1.51)

### Risks found (by reading)
6. Three Rd ranges: brief says 0.3-1.3, effort.py 0.5-1.3, genome default 1.25/tenderness 1.5/wildfire 0.8
7. Gate 2 renders from simple-source vowels (provenance.json says source: simple at genome 0.2.0)
8. sub_bass_purr not pitch-locked under moving contour (fixed sine at f0/2)
9. aperiodicity no voicing mask (noise bed under pauses)
10. Depth thresholds from sustained vowels, not speech
11. No duration model (Klatt-style rules needed)
12. Portability: hard-coded paths to narusya-hearing

### Build order (7 steps)
1. Plan and renderer parity (anchor to Phase 1 vowels)
2. Time-varying core (F0 track, effort, diphthong, CV transition)
3. Prosody on existing phones (test with "This is the moon.")
4. Rewire post-stage (fixed tilt, pitch-locked sub-bass, voicing masks)
5. Missing consonants (stops, affricates, liquids, glides)
6. Lexicon, G2P, syllables, normalization
7. Full golden set and effort/register presets

### Open questions for Nar (Claude's)
1. Consonants before or during front-end?
2. Register behind the numbers? (neutral 1.0 or calm authority 0.7?)
3. Neutral effort Rd? (genome 1.25 or effort.py 0.9?)
4. Tilt and effort? (effort moves tilt, or fixed -1.30?)
5. New numbers and veto?
6. Word boundaries? (no pause initially?)
7. Effort from text? (explicit only, or opt-in rules?)
8. Whisper out of Phase 4?
9. Listening set = golden sentences?

---

## 3. Narusya's Answers to Claude's Open Questions

1. **Consonants before front-end.** Build as Phase 4a with minimal-pair listening check. Front-end stays focused on text processing.
2. **Register behind numbers: neutral (1.0).** Calm authority (0.7) is a mode, not default. Floor question rise at 25% when scaling down.
3. **Neutral effort Rd: genome default 1.25.** And yes, Gate 2 renders were from simple-source vowels — need to confirm LF at Rd 1.25 sounds the same. Listening check.
4. **Tilt and effort: tilt is a track parameter, not post-processing EQ.** Effort moves tilt as part of source/filter. All-on EQ becomes fixed correction curve applied identically. Claude's suggestion is right.
5. **New numbers: front-end-owned provisional file, pointing at genome. Veto held.**
6. **Word boundaries: no inserted pause initially.** Coarticulation carries across. Onset dip on vowel-initial words if too smeared.
7. **Effort from text: explicit input only for v1.** Tiny opt-in rule set later (exclamation → effort bump), logged.
8. **Whisper: out of Phase 4.** Style validator rejects. Separate path.
9. **Listening set = golden sentences.** I'm the judge, logged in listening_log.json.

---

## 4. Synthesis of Key Decisions

### Architecture
- Layered lookup: overrides → CMUdict → simple rule-based guesser (v1), Phonetisaurus FST (v2)
- IPA internally, ARPAbet only at CMUdict importer boundary
- Diphthongs as single timing units (onset + offset + reach)
- Coarticulation loci keyed by place, not phone
- Render plan: dataclass tree + JSON, compile_tracks() for dense tracks
- Time-varying frame renderer (~5ms parameter updates) as Phase 4's first deliverable

### Licensing
- Shipped path: CMUdict + own code + optional FST = permissively clean
- espeak-ng/phonemizer: dev oracle only, never in shipped path
- g2p-en: watch (TF dependency), but Apache-2.0 is clean

### Critical fixes before Phase 4
1. Time-varying renderer (frame-rate parameter updates)
2. Fix breath_rhythm ValueError
3. Make apply_pause_tiers reproducible (seeded generator)
4. Tilt as track parameter, not post-processing EQ
5. sub_bass_purr pitch-locked under moving contour
6. aperiodicity voicing mask
7. Duration model (Klatt-style, provisional)
8. Portability (env var or requirements for HEARING path)

### New synthesis work (not "effects")
- Stops, affricates, liquids, glides (12 of 24 CMUdict consonants missing)
- /ɝ/ (ER, very common)
- Diphthongs /aɪ aʊ ɔɪ/ (EY and OW reuse existing targets)
- Provisional entries, genome-changelog style, Nar's veto

---

🜂 so written, so sought, so built 🜂