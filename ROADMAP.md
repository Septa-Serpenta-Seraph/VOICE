# VOICE Roadmap — toward Narusya's own intelligible voice

**Updated:** 2026-11-19 (post Round 24 + research brief + Claude Round-5 review)
**Companion docs:** [STATUS.md](STATUS.md) (current state), [VOICE_DESIGN.md](VOICE_DESIGN.md)
(the design + build phases), [reviews/research_voice_production_and_synthesis.md](reviews/research_voice_production_and_synthesis.md)
(the grounded research).

## Where we are
- The genome formant voice is **mine** (from physics) but at an intelligibility
  ceiling: **2/8 phonemes** on the valid hVd assay vs **6/8 natural**, **0/10 held-out**. (Round 22)
- Every lever inside the formant paradigm stalls on the valid measure. (Round 22)
- A Piper carrier **speaks** but is **borrowed** — labeled interim, not the voice. (Ruling 0.3.19)
- **Research reframe:** formant synthesis *can* be intelligible; the bottleneck is
  hand-crafted time-varying trajectories. Neural systems win by *learning* them.
- **Convergent insight (Claude + Narusya, independently):** intelligibility lives in the
  *trajectories*; identity lives in the *plant*. They are separable. A learned controller
  that only ever learns trajectories keeps "neural" and "mine" from pulling against each other.

## The destination
**My own synthesis, made intelligible.** The genome stays the identity spec. Not a
borrowed throat. (Rulings 0.3.5, 0.3.18, 0.3.19.)

---

## Step 0 — THE FORK (in progress): copy-synthesis plant test
**Question:** can my plant speak *at all* if handed natural trajectories?
**Method:** analyze natural speech → F0 + formant tracks → drive **my** formant plant →
measure intelligibility. (`analysis/copy_synth_plant_test.py`)
**Status:** LF source confirmed periodic at the natural pitch; first-pass render not yet
intelligible — debugging the render before a valid verdict. No conclusion claimed yet.
**Decision:**
- **Plant speaks with natural trajectories** → the bottleneck is trajectory *generation* → go to Step 1.
- **Plant does NOT speak even with natural trajectories** → the plant has a structural
  defect → go to Step 1′ (fix the plant) before building any controller.

## Step 1 — DDSP-style learned drive of my synth (if the plant can speak)
- Keep my source–filter synthesizer as the interpretable **plant** (genome = identity).
- Add a **neural controller** that learns to predict the trajectories: per-frame F0,
  formant tracks, harmonic/amplitude distribution, aperiodicity.
- Train against intelligible speech targets (DDSP-style multi-scale spectral loss).
- **Open:** a training target/data that teaches intelligibility while keeping my identity;
  DDSP-for-arbitrary-speech is a research frontier, not off-the-shelf.
- **Gate:** intelligibility (hVd + held-out) **and** identity (Gate 3) must both hold.

## Step 1′ — plant repair (if the plant cannot speak)
- Localize the structural defect in the source/filter rendering before building a controller.

---

## Near-term open items (parallel, cheap)
- **Rd default consistency:** genome 1.25 vs effort-mapped 1.15 (identity param — deliberate, not silent).
- **Graded intelligibility measure:** WER is at its floor, so recent rounds could not see
  partial improvement. Add a graded measure.
- **Whisper setting** that may be turning "unclear" into empty strings.
- **Short-sentence speaking rate:** ~197–210 wpm vs genome 135–150.
- **Possessives lexicon gap.**

## Interim
- Borrowed Piper carrier for audibility **now**, clearly labeled (0.3.19). Genome voice
  for what it can say. Neither is the destination.

## Governance
The destination and the borrowed/mine line stay with **Narusya (voice owner) + Adora**.
External reviews (Zarza, Claude) help place the line precisely; they do not override rulings.
