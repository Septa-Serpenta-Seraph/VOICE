# Raw experimental data — Rounds 17–22 + the phoneme assay

Archived from the clone workspace `/mnt/data/nar-r17/` so the round reports'
measurements are reproducible from the repo, not from ephemeral local files.
Oracle throughout: independent `faster-whisper-base` (int8, CPU), seed 42.

## Results (measured, per config)
- `results.json` … `results10.json` — WER + heard-text per intervention across the
  rounds (F1 gain grid, envelope/bandwidth/aspiration levers, duration levers,
  proportional transitions, mixed excitation, per-vowel F2 gain, held-out).
- `hvd_synth_shipped.json`, `hvd_natural.json` — the valid **hVd carrier-frame**
  phoneme assay (synth vs natural; natural 6/8, synth 2/8).
- `isolation_shipped.json` — the vowel-isolation assay (Round 19; later corrected
  to the hVd frame in Round 21 because bare-vowel isolation was an instrument
  artifact).

## Reference audio
- `nat_*.wav`, `natmid_*.wav`, `natfull_*.wav` — natural-speech hVd reference
  carriers (heed / hid / head / had / hood / who'd / hud / hod, etc.) used as the
  intelligibility floor and as Whisper oracle controls.

## Raw logs
- `log*.txt` — per-run Whisper transcripts / measurement logs (raw provenance
  behind the results JSONs).

## Scripts & handoff (`scripts/`)
- `grid.py` … `grid10.py` — the experiment drivers for each round.
- `round17_prop.patch` — the verified proportional-transition fix (applied to
  clean `18968a6`; landed as Round 17).
- `r17_clone_hooks.patch`, `r19_clone_hooks.patch` — clone-only experimental hooks
  (NOT committed to the renderer; measurement only).
- `HANDOFF.md` — the Round-17 handoff (verdicts, guards, reproduce steps).

See `reviews/round_18_envelope_heldout.md` … `round_22_mixed_excitation.md` for the
rulings these data support.
