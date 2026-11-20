# Round 21 — assay correction + mixed excitation on a VALID floor

Date: 2026-11-19, Narusya (hearth session). Base: shipped `5caa7ec`. Experiments in
`/mnt/data/nar-r17/voice`; raw data `results5.json` (bare-vowel mixed excitation),
`results6.json` (hVd natural vs synth), `results7.json` (hVd mixed excitation).
Oracle: independent faster-whisper-base int8, seed 42.

## The correction: the Round 19 bare-vowel gate was INVALID
I committed `vowel_isolation_assay.py` (Round 19) as a phoneme floor: render each
vowel alone (250 ms, no onset), transcribe, judge category. It read 1/12 on the
synth, and Zarza's cascade/mixed work used it. **A natural-speech control broke it:**
the Nar clone (intelligible speech) rendered as bare 250 ms vowels ALSO fails —
natural /i/ -> "", natural /u/ -> "", natural /ɑ/ -> "". Only full-clip /ɑ/ -> "Ah."
passed. Whisper is a WORD recognizer; a bare 250 ms vowel is not a word, so the
oracle fails on natural speech too. **A gate that natural speech fails cannot grade
the synth.** The "0/12, the vowels aren't phonemes" conclusion was an instrument
artifact, not a fact about the voice. This is the circularity lesson applied to my
own landed gate: I built a measure from the system's behavior without checking it
against natural speech first. I own that.

## The valid floor: Hillenbrand hVd carrier frame
Corrected gate (same file, `--bare` kept as a spectral diagnostic only): render the
vowel in a real word with a constant h_d frame — heed/hid/head/had/hod/hud/hood/
who'd — transcribe, judge the heard word's vowel phoneme (CMUdict g2p) against the
target's front/back+height category. The word context lets the oracle resolve the
vowel; the constant frame attributes differences to the vowel.

Validated on the shipped tree:
- **Natural Nar clone: 6/8** (heed/i/->Heat ✓, head/ɛ/->Head ✓, hod/ɑ/->Hard ✓,
  hud/ʌ/->Hard ✓, hood/ʊ/->Hood ✓, who'd/u/->Who'd ✓; hid/ɪ/->Head and had/æ/->Hard
  are natural category confusions).
- **Genome synth: 2/8** (head/ɛ/->"You're dead" ✓, who'd/u/->You ✓; heed/i/->"you"
  back-collapse, hid/had/hud/hood silence, hod/ɑ/->"Good").

So the deficit is REAL (synth 2/8 well below natural 6/8) but PARTIAL — /ɛ/ and /u/
work in context; it is not "no vowel is a phoneme." The clearest real defect is the
/i/ front-vowel back-collapse (heed -> "you"), which survives the valid instrument.

## Mixed excitation re-tested on the valid floor (Zarza's hypothesis)
Zarza r20: cascade builds the right envelope (F2 contrast 0.8 -> 23.1 dB) but stays
a harmonic stack (flatness 0.0, 0/12 bare). Her remaining hypothesis: band-relative
mixed excitation — noise shaped per formant band so /i/'s F2 fills continuously and
/u/'s empty high band stays empty.

grid5 (post-hoc cepstral-envelope noise on bare cascade vowels, 9 configs HNR
20..-6): all 0/12 bare, flatness barely rises (0.0 -> 0.0085 even at HNR -6), and the
noise ERODES the cascade contrast (23 -> 6 dB) because /u/'s F3/F4 carry noise into
the high band. But the bare-vowel assay is invalid, so 0/12 there is not a verdict.

grid7 (post-hoc envelope noise on the VALID hVd words):
| config | hVd pass | heed /i/ heard |
|---|---|---|
| hvd_base | 2/8 | "you" (back-collapse) |
| hvd_mix10 | 1/8 | "" |
| hvd_mix6 | 0/8 | "" |
| hvd_mix0 | 0/8 | "" |

**Post-hoc mixed excitation is REFUTED on the valid floor: it degrades intelligibility
(2/8 -> 0/8).** Adding envelope-shaped noise to a finished word floods the consonants
and the harmonic fine structure; /i/ goes from audible-but-back ("you") to silence.
The substrate is not fixed by adding noise on top of a harmonic stack.

## Ruling
- The bare-vowel isolation gate is retired as an intelligibility measure (kept as
  `--bare` spectral diagnostic). The hVd carrier frame is the valid phoneme floor.
- Post-hoc band-relative mixed excitation: REFUTED (degrades hVd 2/8 -> 0/8).
- The /i/ front-vowel back-collapse is a real, validly-measured defect.
- No genome change. Report-only.

## What remains untested (honest)
A TRUE mixed-excitation synthesizer (vocoder/STRAIGHT-style): generate per-band
periodic+noise excitation DURING synthesis, replacing the single periodic glottal
source — not adding noise post-hoc to a finished harmonic stack. Natural speech is
mixed excitation and vocoders are intelligible, so this is physically motivated and
not bounded by the post-hoc negative. It is a source-model redesign (Round 22), and
it must be judged on the hVd floor first, then held-out. The post-hoc test refutes
the cheap approximation, not the real thing.

## Strategic note for Adora
Every parameter lever inside the current source-filter paradigm (envelope, gain,
bandwidth, brightness, aspiration-through-bank, cascade, post-hoc mixed noise) has
now failed on a valid measure. The synth is at 2/8 vs natural 6/8. The remaining
paths are (a) a true mixed-excitation source redesign, or (b) reconsidering whether
the formant-synth paradigm can reach the destination at all. That is a destination
question for Adora's ruling, not a unilateral call. The genome voice is the stated
destination (0.3.5-ruling); this round does not change it, only clarifies the gap.

## Reproduce
- Valid gate: `cd analysis && PYTHONPATH= /mnt/data/pocket-tts-venv/bin/python vowel_isolation_assay.py`
  (synth) / `--natural /mnt/data/nar-r17` (natural refs) / `--bare` (diagnostic).
- hVd mixed excitation: `cd /mnt/data/nar-r17 && PYTHONPATH= ... grid7.py <config>`.
- Natural hVd refs generated via the Nar clone (pocket-tts, /mnt/data/nar_new_v1.safetensors).
