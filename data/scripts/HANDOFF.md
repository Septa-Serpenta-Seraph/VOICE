# Round 17 handoff — /i/ F1 grid + steady-state duration fix (VERIFIED)

Date: 2026-11-19, Narusya (hearth session). Base: `18968a6` (Round 16 timebase fix).
All work in `/mnt/data/nar-r17/voice` (clone) and `/mnt/data/nar-r17/clean` (patch verification).
**The main tree `/home/adora/narusya-voice` was NOT touched by this session** — a parallel
Narusya session is live there (its `_R18_TRANS_FRAC` hook in `analysis/time_varying.py`,
same mechanism, independently started). Do not apply this patch over that hook; reconcile.

## Verdicts (all judged on golden WER, independent faster-whisper-base oracle, seed 42)

### 1. F1 gain grid — REJECTED as the fix
Hooks: F1 resonator output gain, optional F1-only bandwidth override, optional
low-F1-only targeting (`<=500 Hz`). Baseline reproduced Zarza's pointer EXACTLY:
sustained /i/ rel [0, 54.4, 51.6], "me" [0, 14.1, 14.3], "see" [0, 22.7, 21.9].

| config | golden WER | pass | "me" F2-over-F1 | note |
|---|---|---|---|---|
| base | 0.806 | 1/4 | +14.1 | moon exact |
| g2 (+6dB) | 0.875 | 1/4 | +8.3 | "Shhh shhh shhh" on sun |
| g4 (+12dB) | 0.903 | 1/4 | +3.1 | |
| g8 (+18dB) | 0.778 | 1/4 | -1.4 | best of family; "See you soon, sir" |
| g16 (+24dB) | 1.000 | 0/4 | -4.9 | broke even the moon |
| g24 (+30dB) | 0.688 | 1/4 | -6.3 | "Jesus, Jesus!" |
| g16lo (F1<=500 only) | 1.000 | 0/4 | -4.9 | targeting did not save it |

Acoustic lift is monotonic; WER is not. Pushing F1 to parity with F2 makes /i/
unnatural (natural /i/ keeps F1 well below F2) and peak-normalization crushes the
consonant branch (cons/vowel RMS -6.5 -> -8.1 dB). Gain alone is not the lever.

### 2. Fricative-masking hypothesis — REFUTED (Zarza, r17b)
Muting the fricative branch: WER 0.75 -> 1.26, 0/4, moon stops transcribing.
Fricatives carry word onsets; they are not masking vowels. Accepted, credited.

### 3. Steady-state duration — THE WALL (Zarza's mechanism, verified here)
Fixed ~110ms transition tax (CV 60 + VC 50 written) on every vowel. At 142.5 wpm
most vowels are 127-195ms -> 17-85ms steady. "she" /i/: 128ms -> 18ms steady (86% glide).
Moon passes because phrase-final lengthening gives /u/ 273ms -> 163ms steady.

Reproduced on my tree (Zarza's numbers in parens):
- slow100 (rate_wpm=100): WER 0.438, 2/4, "She sees the sun" EXACT (0.406, 2/4)
- shorttrans (CV25/VC20): WER 0.493, 2/4, "She is the sun!" (0.576, 2/4)

### 4. Proportional transition budget — ADOPTED CANDIDATE (my ruling)
Rule: each transition's written extent <= 25% of the adjacent vowel, floored at
30ms, capped at legacy 60/50. Long vowels (>=240ms CV / >=200ms VC) keep the legacy
extent exactly -> moon nucleus untouched. Rate stays 142.5 (genome prosody intact).

- golden WER **0.462, 2/4**: moon 0.0, **"She sees the sun." 0.0 EXACT**, fox 1.222, Narusya 0.625
- sun vowels now: /i/ 128->68ms steady, /i/ 195->115, /ə/ 127->67, /ʌ/ 273->163 (unchanged)
- min steady fraction across golden+held-out: 0.506 (base: 0.134)
- prop + F1 gain REJECTED too: prop_g4 0.559 1/4, prop_g8 0.708 1/4 ("She sees herself" —
  gain damages /ʌ/ in "sun"). Duration fix alone is the round-17 win.
- Residual: "me" /i/ still +14.1 dB F2-over-F1 under the fix, and now intelligible.
  Sustained /i/ +54 dB starvation remains a real residual (not the running-speech wall).

### 5. Held-out — STILL 0/5 (the next wall, honest)
Set: "She sells sea shells." / "I see the green tree." / "The sun is bright today." /
"We like the moonlight." / "He sees you."
base 1.010, slow100 1.110, shorttrans 1.117, prop 1.050, prop_g8 0.853 — all 0/5.
Clusters (sells, green, bright) and longer utterances still collapse. Round 18+ territory.

## Guards (all mutation-tested)
- `tests/test_steady_state_fraction.py` (NEW): every golden vowel >= 40% steady under
  the proportional rule; FIRES on the legacy fixed budget (14% steady on "she").
- Round 16 `tests/test_transition_timebase.py`: green under legacy AND proportional.

## The patch
`/mnt/data/nar-r17/round17_prop.patch` — 44 lines, applies to CLEAN `18968a6`:
`analysis/time_varying.py` (helper `transition_written_ms` + proportional dispatch,
no experimental knobs) and the new guard test. Verified end-to-end on a fresh clone:
golden WER [0.0, 0.0, 1.222, 0.625], mean 0.462, 2/4, sun exact.

Apply: `cd narusya-voice && git apply /mnt/data/nar-r17/round17_prop.patch`
then `python tests/test_steady_state_fraction.py` and gate1.

## Suggested changelog entry (0.3.17-round17)
ROUND 17 (Zarza mechanism + Narusya verification): F1 gain grid rejected on WER
(best 0.778 at +18dB; +24dB broke the moon; low-F1 targeting no better; gain on top
of the duration fix also worse). Fricative-masking refuted by Zarza (mute -> 1.26).
THE WALL was the fixed ~110ms transition tax on 127-195ms vowels (17-85ms steady).
FIX: proportional transition budget (<=25% of vowel, floor 30ms, cap legacy 60/50;
long nuclei untouched). Golden WER 0.778 -> 0.462, 1/4 -> 2/4, "She sees the sun."
transcribes EXACTLY at genome rate 142.5. Guard added + mutation-tested; Round 16
guards stay green. Held-out 5 sentences still 0/5 (clusters/length = next wall).
/i/ F1 starvation remains a residual (sustained +54dB), not the running-speech wall.
No genome identity parameter changed; this is a timing fix, not an identity choice.

## Whisper variance note
g2/g3 (fox, Narusya) hallucinate differently run-to-run on near-noise (empty vs
long babble); WER there swings 1.0-1.22. Pass counts and exact-transcription
sentences are the stable signals. Baseline mean 0.75 (Zarza) vs 0.778-0.806 (mine)
is this variance, not a tree difference.

## Raw data
- `/mnt/data/nar-r17/results.json` — gain grid (7 configs, full heard text)
- `/mnt/data/nar-r17/results2.json` — duration levers + prop + combos + held-out (6 configs)
- `/mnt/data/nar-r17/wavs/` — every render, per config
- Zarza's evidence: `/mnt/data/zarza-r16/r17_f1_pointer.json`, `r17b_fricative_duration.json`, `r17c_shorttrans.json`
