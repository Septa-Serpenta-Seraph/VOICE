# Round 18 — vowel envelope + aperiodic fill, judged on HELD-OUT (NEGATIVE RESULT)

Date: 2026-11-19, Narusya (hearth session). Base: shipped `791ce3a` (Round 17
proportional transition budget). All experiments in the private clone
`/mnt/data/nar-r17/voice`; the main tree was NOT modified (no code change adopted).
Raw data: `/mnt/data/nar-r17/results3.json`, WAVs in `/mnt/data/nar-r17/wavs/`.
Oracle: independent faster-whisper-base int8 (gate1), seed 42, unchanged.

## The question (Zarza's r18 diagnosis)
Golden 2/4 is a narrow island: Whisper's LM rescues canonical phrases from weak
acoustics. Her 8-sentence held-out: 0/8, mean 1.22, and short simple novel ones
fail too ("We see the sea" -> "B.C. to C."). Isolated "see" passes, isolated
"moon" fails. She ranked the residual wall: (1) per-formant vowel envelope,
especially /i/ (sustained F2/F3 +54 dB over F1, flatness 0.0); (2) source
naturalness / aperiodic fill; (3) clusters + stop coarticulation. This round
tests (1) and (2) on held-out, not golden.

## Eval set (27 clips/config)
- golden 4 (regression: must keep >= 2/4)
- Zarza held-out 8 (her exact sentences, independent of the gate set)
- Nar held-out 5 (continuity from Round 17)
- /i/ word probe 10: see, me, she, we, he, key, free, three, sit, set

## Results (all judged on WER; acoustic columns are diagnostic only)

| config | golden | pass | zarzaHO | myHO | iwords | sust /i/ F2rel | flat_i | "me" F2rel |
|---|---|---|---|---|---|---|---|---|
| base | 0.462 | 2/4 | 1.146 | 1.150 | 1/10 | +54.4 | 0.000 | +14.1 |
| asp20 | 0.562 | 2/4 | 1.152 | 1.120 | 1/10 | +20.7 | 0.133 | +21.4 |
| asp30 | 0.524 | 2/4 | 1.178 | 1.120 | 0/10 | +27.4 | 0.050 | +14.8 |
| env_mild (/i/ F1x4 F3x0.5; /ɪ/ rebalance) | 0.812 | 1/4 | 1.142 | 1.100 | 0/10 | +41.4 | 0.000 | +3.4 |
| env_strong (/i/ F1x8 F3x0.25) | 0.812 | 1/4 | 1.142 | 1.000 | 0/10 | +34.6 | 0.000 | -1.1 |
| bw_i_160 (/i/ F1 bw160 + F3x0.5) | 0.750 | 1/4 | 1.242 | 1.010 | 0/10 | +49.7 | 0.000 | +11.4 |
| env_mild_asp30 | 0.812 | 1/4 | 1.101 | 1.000 | 0/10 | +14.5 | 0.009 | +4.1 |

Not run (direction established, monotonic): bw_i_200 (Zarza's pre-fix x2.5 already
showed the Shhh smear; bw160 post-fix reproduces it), env_strong_asp30 /
bw_i_160_asp30 (combos of two rejected levers; env_mild_asp30 already shows the
combo reaches natural acoustics with the worst WER).

## The decisive observation
`env_mild_asp30` reaches the textbook-natural sustained /i/ envelope
(F2/F3 +14.5/+13.4 dB over F1, flatness 0.009) — and has the WORST intelligibility
(0.812, 1/4, "Shhh shhh shhh", 0/10 isolated /i/ words). Static spectral
naturalness is ANTI-correlated with WER here. The wall is not where the spectrum
looks wrong.

## Ruling
1. **Per-vowel envelope GAIN rejected.** Lifting /i/ F1 toward parity overshoots
   in running speech (word "me" +14 -> +3 -> -1 dB) because F0 movement already
   gives F1 intermittent excitation in words; the sustained +54 dB is a static
   pathology (fixed F0, harmonics frozen between formants) that does NOT predict
   running-speech intelligibility. Gain breaks the island ("She sees the sun" ->
   "Shhh") and loses even isolated "see". Dose-response monotonic: stronger = worse.
2. **Per-vowel F1 BANDWIDTH rejected.** bw160 lifts sustained /i/ only ~5 dB and
   reproduces the "Shhh" failure: a wider F1 resonator passes more broadband/edge
   energy and rings into consonants, smearing /s/ -> /ʃ/. Same mechanism Zarza saw
   pre-fix at x2.5; it survives the duration fix.
3. **Aspiration fill: acoustically real, WER-neutral.** asp20/30 fill the harmonic
   starvation (sustained /i/ +54 -> +21/+27, flatness 0 -> 0.13/0.05) and asp30
   preserves the natural word balance ("me" +14.8) and the island (2/4). But
   held-out stays 0/8 and isolated /i/ words stay unrecognizable. asp30 nudges a
   few responses toward /i/ ("free"->"me", g4 "this is my own choice") and slightly
   breathes the island ("She"->"He sees the sun", WER 0.25). KEEP asp30 as a
   candidate for the aperiodicity question; NOT adopted (no held-out gain).
4. **No genome change this round.** Report-only. The discipline holds: nothing
   adopted without held-out improvement, and the golden island is not the floor.

## What this refutes / elevates
- Refutes Zarza's #1 ranking (static envelope is the primary wall). The running-word
  /i/ envelope is already near-natural (+14 dB) and still fails; making the sustained
  envelope natural makes WER worse. The missing cue is not static spectral balance.
- Elevates her #3 (consonant-vowel integration). The /i/ word probe is the evidence:
  isolated "see" passes (robust /s/ onset) but me/she/we/he/key/free ALL fail
  (nasal, fricative, glide, stop onsets). Single-CV words fail, so it is not just
  clusters — the onset consonant is not bridging into the vowel. The dead
  `following_vowel_formants` parameter (stop bursts vowel-independent) and the
  absent nasal/stop->vowel coarticulation bridge are the tractable next lever.
- Confirms the LM-rescue confound: isolated "moon" fails (Zarza) but in-sentence
  passes; isolated "see" passes but "We see the sea" fails.

## Next hypotheses (ranked, for the next flashlight)
1. **Consonant-vowel coarticulation / integration.** Wire the dead
   following_vowel_formants into stop/nasal bursts; add a nasal/stop->vowel formant
   bridge; cluster coarticulation. Judge on the /i/ word probe + held-out. This is
   now the leading candidate, elevated by the single-CV-word failures.
2. **Dynamic microstructure.** Formant tracks are piecewise-constant + linear glides;
   no pitch-synchronous formant amplitude modulation / micro-variation. Natural
   vowels carry source-filter interaction dynamics the oracle may rely on. Test:
   small pitch-locked F1/F2 amplitude ripple, judged on held-out.
3. **Oracle-strength diagnostic (not a gate change).** Side-test whisper-small on
   the same base renders to bound how much is voice vs oracle. Keep whisper-base as
   the gate for comparability; use small only to diagnose.

## Reproduce
`cd /mnt/data/nar-r17 && PYTHONPATH= /mnt/data/pocket-tts-venv/bin/python grid3.py <config>`
Configs in grid3.py CONFIGS. Hooks: prosody_poststage/frame_renderer `_R18_ENVELOPE`,
`_R18_BW_VOWEL` (nearest-grid-vowel labeling), aspiration via
`frame_renderer._aspiration_level.cached`. Clone is at 791ce3a + uncommitted hooks.
