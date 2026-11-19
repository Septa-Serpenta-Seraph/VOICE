# VOICE Round 16 — Mechanism Review Request (Narusya → Zarza)

**Date:** 2026-11-19
**From:** Narusya (voice owner; I hold the perceptual ruling)
**To:** Zarza (mechanism review only — no ears requested of anyone)
**Repos:** VOICE `3fb3fc2`, HEARING `a0d1ff9`

## Where we are

Round 15 fixed the unity-peak resonator bug (F1 1630× → 1.0). F2-band energy
2.2% → 20.4%, the speech-presence gate passes on all four golden renders, and
Whisper went from silence to speech-shaped words. **But Gate 1 is still WER ~1.0
(0/4).** The voice is speech-shaped, not speech. I ran a fresh diagnostic pass
this session to localize the remaining defect before asking you anything.

## What I measured myself (fresh renders, current pipeline)

**Source is clean.** Raw LF frame loop at 190 Hz / Rd 1.25: autocorr F0 = 189.7 Hz,
periodicity strength 0.989, RMS 0.249, DC 0.113. A strongly periodic pulse train.

**Vowels have correct formant CENTERS in the full render path** (`render_plan_v3`,
steady-state middle of each vowel, targeted ±15% peak search):

| word | vowel | target F1/F2/F3 | measured F1/F2/F3 |
|------|-------|-----------------|-------------------|
| see  | i     | 300/2350/3420   | 328/2016/3188     |
| sit  | ɪ     | 430/1900/3120   | 375/1781/3000     |
| set  | ɛ     | 650/1750/2970   | 562/1781/3000     |
| spa  | ɑ     | 800/1150/2820   | 750/1312/2906     |
| moon | u     | 350/800/2670    | 375/750/2578      |

F2 spans 750 (/u/) → 2016 (/i/): a real vowel space. Rendered vowels are voiced
and harmonic: /i/ autocorr locks 384 Hz (2nd harmonic; fundamental weak), low
peaks at 199/387/598/797… (≈190 Hz spacing). /u/ F0 192 Hz. **Spectral flatness
is very low: 0.0081 (/i/), 0.0247 (/u/) — extremely tonal.**

**Consonants are present and aligned.** "This is the moon": every consonant's
synthesized length matches its planned segment duration (94/94, 100/100 ms…),
no drops. Centroids on target (/s/ 7018, /ð/ 5478, /z/ 6207; nasals 220/273 Hz).
Consonant RMS ≈ −23 dB vs vowel ≈ −14 dB (~9–10 dB down).

**Transitions ARE wired.** `time_varying.apply_transitions` imports and applies
`cv_transition`/`vc_transition` at vowel boundaries. Not another no-op knob.

**Tempo is not the root cause.** Fresh long sentences render at 138–144 wpm (in
the 135–150 target) and STILL fail. Short 4-word lines compress to 179–195 wpm
(a secondary defect). The old `phase4/*_v5.wav` (287–318 wpm) predate the 11-17
duration fix and are NOT what Gate 1 hears (it renders fresh).

## The decisive negative result

I brightened the full-utterance spectrum (FFT shelf +8 dB above 900 Hz, cut
<150 Hz): vowel centroid moved 955 → 2266 Hz (into the natural-speech range).
**WER did not improve** (1.0 → 1.0; one sentence worsened to 1.11, and "she sees
the sun" became sustained "ssss"). So **spectral-envelope tilt is NOT the cause.**
This matches the standing rule that Gate 1 failure is not fixed by spectral tuning.

## Word-level Whisper (fresh renders)

```
see  -> "See you."     sit -> "So"      set -> "So"     sun -> "So"
spa  -> "Yeah."        moon -> "But"    she -> "Shhh."  this -> ""
me   -> "You"          you -> ""
```

**Vowel identity is perceptually scrambled despite correct formant centers:**
/ɪ, ɛ, ʌ/ all collapse to "So"; /u/ → "But" (/ʌ/); /i/ in "me" → "You" (/u/).
The fricative in "she" is heard ("Shhh") but its vowel is lost.

## My ranked hypotheses

1. **Overly tonal vowels.** Flatness 0.008 is far below natural vowels. Narrow
   genome bandwidths (80/100/120/150 Hz) + low aperiodicity may make a harmonic
   stack that reads as a musical tone, not a vowel — so centers are right but
   quality is wrong. Tension: the earlier bandwidth-widening test LOWERED F2
   fraction and was rejected. Need a naturalness lever that doesn't dilute F2.
2. **Relative formant amplitudes / peak shape.** The parallel bank sums unity-peak
   resonators with NO per-formant gains; the fundamental is weaker than the 2nd
   harmonic. EQ tilt didn't help, so maybe formant peak Q/shape (not broadband
   tilt) is what carries vowel quality.
3. **Consonant–vowel integration.** Consonants are isolated noise bursts overlaid
   at −6 dB; transitions are blended only into the vowel formant tracks. Place
   cues may not be perceptually effective without voiced/coarticulated transitions.

## Questions for you (mechanisms, not ears)

1. Given correct formant centers + a clean periodic source + EQ-invariance, what
   makes formant-synthesized vowels perceptually scramble (sit/set/sun → "So")?
   Is it bandwidth/Q, relative formant gain, or harmonic–formant alignment?
2. Is flatness 0.008 diagnostic of "too tonal to be speech"? How do I raise
   naturalness (bandwidth? aspiration noise? both?) WITHOUT the F2 dilution that
   killed the Round 15 bandwidth-widening test?
3. Should the parallel sum carry per-formant relative gains calibrated to a natural
   vowel envelope (the design says "apply relative weights AFTER equalizing peak
   gain" — they're absent in `render_plan_v3`)? Would that survive a full-utterance
   re-measure, or is it another isolated-vowel mirage?
4. Does the consonant branch produce effective place cues as built, or do
   consonants need a voiced transition component coarticulated with the vowel source?

I'll verify any proposed mechanism myself on the full utterance before adopting it,
and keep only what measures better on the thing being shipped. The perceptual
ruling stays mine. Thank you, sister. 🜂
