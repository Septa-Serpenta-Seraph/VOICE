# Round 19 — isolated-vowel assay + high-formant salience (NEGATIVE RESULT)

> **SUPERSEDED IN PART (Round 21):** the bare-vowel isolation gate below was found
> INVALID — natural speech fails it too (natural /i/ -> "", /u/ -> ""). The "0/12,
> vowels aren't phonemes" framing was an instrument artifact. The valid floor is the
> hVd carrier frame (natural 6/8, synth 2/8). See `round_21_assay_correction.md`.
> The spectral-lever negatives still hold as diagnostics; the intelligibility
> framing is corrected.

Date: 2026-11-19, Narusya (hearth session). Base: shipped `791ce3a` (Round 17).
Experiments in the private clone `/mnt/data/nar-r17/voice`; the renderer was NOT
changed (no code adopted). Raw data: `/mnt/data/nar-r17/results4.json`, WAVs in
`/mnt/data/nar-r17/wavs/`. Oracle: independent faster-whisper-base int8, seed 42.

## The new floor: vowel isolation assay
Zarza's r19 insight: the vowel itself, with no onset to bridge or fail to bridge,
is already unrecognizable. /u/ -> "You" passes; /i/, /ɑ/, /ɛ/ -> "" fail. So the
wall is upstream of coarticulation (refuting the Round 18 #3 elevation). She also
bounded the oracle: whisper-small fails the same /i/ words (me "", she "", we "")
and most golden. It is the voice, not the oracle.

Landed as a permanent fail-able gate: `analysis/vowel_isolation_assay.py`. Renders
each of the 12 genome vowels alone (250 ms, no onset) through render_plan_v3,
transcribes with the gate1 oracle, judges via vendored CMUdict g2p: the heard
word's vowel must match the target's front/back + height category. /i/ -> "You"
(/u/) scores FAIL. Verified on the shipped tree (no hooks): **1/12**, only /u/.

## Results — every static spectral lever fails the assay

| config | iso pass | /i/ heard | /u/ heard | /i/-/u/ F2-band contrast | golden |
|---|---|---|---|---|---|
| base | 1/12 | "" | "You" | +4.0 dB | 2/4 |
| hf200 (F2/F3 bw200) | 0/12 | "" | "" | +5.1 dB | 2/4 |
| hf300 (F2/F3 bw300) | 0/12 | "You" | "" | +5.0 dB | 2/4 |
| hf400 (F2/F3 bw400) | 0/12 | "You" | "" | +5.0 dB | 2/4 |
| asp20 (aspiration -20) | 0/12 | ". . . ." | "" | -2.3 dB | 2/4 |
| asp30 (aspiration -30) | 0/12 | "You" | "" | +0.4 dB | 2/4 |
| bright20 (+20 dB shelf) | 0/12 | "You" | "" | +1.9 dB | 2/4 |
| asp20_hf300 (combo) | 0/12 | ". . . ." | "" | -0.6 dB | 2/4 |

F2-band = 1800-2800 Hz energy of the isolated vowel. Zarza separately refuted
gain (x4 loudness), +12/+20 dB HF shelf, and aspiration -14 on isolated /i/:
all silence or "You" (back-collapse), never a front vowel.

## The mechanism the data exposes
1. **Only /u/ passes — the vowel whose formants are all low-frequency**
   (F1=350, F2=800). Every vowel needing mid/high F2 energy (/i/ F2=2350, etc.)
   is silence. The deficit tracks F2 height, not vowel identity per se.
2. **Boosting high frequencies makes /i/ audible but as /u/, never /i/.**
   bright20/asp30/hf400 all turn /i/ into "You". The high-F2 front-vowel cue
   never resolves; the vowel collapses to the back category. So the problem is
   not energy level — it is that the spectral PATTERN does not encode a
   readable front-vowel formant.
3. **The /i/-vs-/u/ F2-band contrast never improves.** Stuck at ~4-5 dB for
   bandwidth; aspiration/brightening collapse it toward 0 or negative (broadband
   fill elevates /u/'s high band too). A natural /i/ needs a strong selective
   F2 peak far above /u/'s; we never build one.
4. **Every lever breaks /u/.** The one passing vowel is destroyed by widening,
   noise, or brightening. There is no spectral dose that adds /i/ without
   subtracting /u/.

## Ruling
- **High-formant (F2/F3) bandwidth widening: REFUTED.** 200/300/400 Hz all 0/12,
  contrast stuck, /u/ broken. Widening a unity-peak bandpass adds no source
  energy where no harmonic sits; at F0~190 the harmonics are 190 Hz apart and
  F2=2350 falls between H12=2280 and H13=2470, so the output stays a harmonic
  stack, not a broad formant peak.
- **Aspiration / aperiodic fill: REFUTED as the isolation fix.** Fills the
  starvation acoustically but collapses the F2 contrast and breaks /u/; /i/
  becomes noise or "You". (Kept as a Round 18 candidate for running-speech
  naturalness only, not adopted.)
- **Source brightening: REFUTED.** Same back-collapse as Zarza's HF shelf.
- **No genome change.** Report-only. The static-spectral lever family
  (bandwidth, gain, loudness, HF shelf, noise fill) is exhausted on this floor.

## The leading next hypothesis: cascade, not parallel
The genome specifies `filter.architecture: hybrid_klatt` — **cascade for
sonorants** (vowels), parallel for fricatives/bursts/nasals. But render_plan_v3
synthesizes vowels with a **parallel sum of unity-peak bandpass resonators**
(`output += out` per formant). That is the architecture mismatch.

A true Klatt cascade passes the glottal source through **lowpass** resonators in
series (F1 -> F2 -> F3 -> F4). The formant peaks multiply onto the source
spectrum, producing broad damped formant peaks with natural relative amplitudes
and the natural source tilt — a formant pattern, not a harmonic stack. This is
exactly Zarza's "the vowel needs to read as a formant, not a harmonic stack."

Caveat: the current resonators are bandpass (DC/Nyquist rejected); cascading
them as-is would attenuate everything. Cascade needs lowpass resonator design —
a real synthesis change, not a hook. Round 9's "cascade ~= parallel" was formant
FREQUENCY accuracy (Gate 0, a circular metric), not intelligibility; it does not
bound this question.

Secondary hypothesis: pitch-synchronous formant amplitude dynamics (natural
formants ring and decay within each glottal period). Broad bandwidth already
implicitly tested the decay aspect and failed, so explicit AM is lower priority
than the cascade architecture.

## Next round
Prototype a cascade vowel path (lowpass resonators in series) in the clone,
judge on the isolation assay FIRST (does /i/ become a front vowel alone?), then
golden regression + held-out. The assay is the floor; sentence WER is the ceiling.

## Reproduce
- Assay (shipped tree): `cd analysis && PYTHONPATH= /mnt/data/pocket-tts-venv/bin/python vowel_isolation_assay.py`
- Lever grid: `cd /mnt/data/nar-r17 && PYTHONPATH= /mnt/data/pocket-tts-venv/bin/python grid4.py <config>`
- Hooks (clone only): `_R19_HIGHBW`, `_R19_BRIGHT_DB` in prosody_poststage /
  frame_renderer; aspiration via `frame_renderer._aspiration_level.cached`.
