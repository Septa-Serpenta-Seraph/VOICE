# Analysis — ⚠️ PENDING RE-MEASUREMENT

Measurements in `narusya_voice_analysis.json` were produced by `analyze_voice.py` v1 and are **method artifacts** — see `VOICE_DESIGN.md` §3.6. Do not use them as design targets.

Specifically:
- **Jitter 2.1%** measures intonation movement, not cycle-to-cycle jitter
- **Shimmer 11.3%** measures loudness change across syllables, not amplitude variation
- **HNR 6.5 dB** is an HPSS energy ratio, not harmonics-to-noise
- **Spectral tilt -136** is actually ≈-4.1 dB/octave (the ×10 multiplier was wrong)
- **F3 2267 Hz** has spurious poles from LPC order 46 at 44.1 kHz
- **F0 range 65–1017 Hz** includes search floor/ceiling artifacts

Re-measurement (Praat-based, voiced frames only, correct units) is pending as Phase 0 work. See `VOICE_DESIGN.md` §5.6 Phase 0 and §10.1.

The raw data is preserved here for reference only.