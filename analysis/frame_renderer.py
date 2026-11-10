#!/usr/bin/env python3
"""
VOICE — Phase 4: Frame Renderer (Step 1)

Time-varying synthesis core. Consumes a RenderPlan, produces audio.
Parameters update every FRAME_MS (5ms). Phase accumulator for LF source.
Resonators carry state across frame boundaries.

Usage:
    python frame_renderer.py --demo     # render "This is the moon."
    python frame_renderer.py --verify   # compare to Phase 1 vowel
"""

import argparse
import json
import os
import sys

import numpy as np
from scipy.signal import lfilter
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_plan import RenderPlan, Style, Segment, PHONE_TABLE, build_plan, SR, FRAME_MS
from phase1_synth import lf_timing_from_rd

SR = 48000
FRAME_SAMPLES = int(FRAME_MS * SR / 1000)  # 240 samples at 48kHz


def load_genome(path):
    with open(path) as f:
        return yaml.safe_load(f)


# ── Effort → Rd mapping ──────────────────────────────────────────────────

def effort_to_rd(effort: float) -> float:
    """Map effort [0,1] to Rd. Genome default 1.25 at effort 0.5."""
    # Linear: effort 0 → 1.5 (tenderness), effort 1 → 0.8 (wildfire)
    # effort 0.5 → 1.25 (genome default, "normal")
    return 1.5 - 0.7 * effort


def effort_to_tilt(effort: float) -> float:
    """Effort → tilt (dB/oct). Range from effort.py: 4.45 dB/oct total."""
    # effort 0: -3.5, effort 1: +0.95 (approx, from effort.py sweep)
    return -3.5 + 4.45 * effort


def effort_to_f0_shift(effort: float) -> float:
    """Effort → F0 shift (multiplicative, ~3% at full effort)."""
    return 1.0 + 0.03 * effort


def effort_to_f1_shift(effort: float) -> float:
    """Effort → F1 shift (Hz)."""
    return 30.0 * effort


# ── LF source with phase accumulator ─────────────────────────────────────

def lf_source_frame(f0_hz: float, rd: float, n_samples: int,
                    phase_state: dict, sr: float = SR,
                    jitter_pct: float = 0.7, rng=None) -> np.ndarray:
    """Generate LF source for one frame using phase accumulator.

    phase_state: dict with 'phase' (current phase 0-1) and 'cycle_pos' (position in current cycle).
    Returns: (source_samples, updated_phase_state)
    """
    if rng is None:
        rng = np.random.default_rng(42)

    tp, te, ta = lf_timing_from_rd(rd, f0_hz)
    t0 = 1.0 / f0_hz
    omega = np.pi / tp
    eps = 1.0 / ta
    alpha = _lf_alpha(tp, te, ta, t0)

    output = np.zeros(n_samples)
    phase = phase_state.get("phase", 0.0)
    pos_in_cycle = phase_state.get("pos_in_cycle", 0.0)

    for i in range(n_samples):
        # Current time within glottal cycle
        t_in_cycle = pos_in_cycle
        period_samples = t0 * sr

        if t_in_cycle < te:
            # Opening phase
            val = np.exp(alpha * t_in_cycle) * np.sin(omega * t_in_cycle)
        else:
            # Return phase
            t_ret = t_in_cycle - te
            t_rem = t0 - te
            val_te = np.exp(alpha * te) * np.sin(omega * te)
            denom = 1.0 - np.exp(-eps * t_rem)
            A = -val_te / denom if abs(denom) > 1e-10 else 0.0
            val = -A * (np.exp(-eps * t_ret) - np.exp(-eps * t_rem))

        output[i] = val

        # Advance
        pos_in_cycle += 1.0 / sr
        if pos_in_cycle >= t0:
            pos_in_cycle -= t0
            # Jitter on next cycle
            jit = rng.normal(0, jitter_pct / 100.0)
            t0 = (1.0 + jit) / f0_hz
            t0 = max(t0, 1.0 / 600.0)  # min F0 600 Hz period

    phase_state["phase"] = pos_in_cycle / t0 if t0 > 0 else 0.0
    phase_state["pos_in_cycle"] = pos_in_cycle

    return output, phase_state


def _lf_alpha(tp, te, ta, t0):
    """Compute alpha for zero DC condition."""
    from scipy.optimize import brentq
    omega = np.pi / tp
    eps = 1.0 / ta

    def integral_opening(alpha):
        return (np.exp(alpha * te) * (alpha * np.sin(omega * te) - omega * np.cos(omega * te)) + omega) / (alpha**2 + omega**2)

    # Find alpha such that integral is zero (approximate)
    try:
        alpha = brentq(integral_opening, -100, 100, xtol=1e-6, maxiter=100)
    except ValueError:
        alpha = -10.0  # fallback
    return alpha


# ── Resonator (single formant, with state carry) ─────────────────────────

def resonator_coeffs(f_hz: float, bw_hz: float, sr: float = SR):
    """Compute lfilter coefficients for a single resonator."""
    w0 = 2 * np.pi * f_hz / sr
    r = np.exp(-np.pi * bw_hz / sr)
    a = [1.0, -2 * r * np.cos(w0), r**2]
    b = [1.0 - r**2]  # gain normalization
    # Actually, simpler: just use the pole
    a = [1.0, -2 * r * np.cos(w0), r**2]
    b = [1.0]
    return b, a


# ── Frame renderer ───────────────────────────────────────────────────────

def render_plan(plan: RenderPlan, genome: dict) -> np.ndarray:
    """Render a RenderPlan to audio.

    Time-varying: parameters update every FRAME_SAMPLES.
    Phase accumulator for LF source. Resonators carry state.
    """
    total_duration = plan.segments[-1].t1 if plan.segments else 1.0
    n_total = int(total_duration * SR) + FRAME_SAMPLES  # pad

    # Initialize
    rng = np.random.default_rng(plan.style.seed)
    phase_state = {"phase": 0.0, "pos_in_cycle": 0.0}

    # Build per-sample parameter tracks
    # We'll process frame by frame
    f0_track = np.full(n_total, 190.0)
    rd_track = np.full(n_total, effort_to_rd(plan.style.effort))
    formant_tracks = {f"F{i}": np.zeros(n_total) for i in range(1, 5)}
    bw_tracks = {f"F{i}": np.zeros(n_total) for i in range(1, 5)}

    # Default formants from genome neutral anchor
    anchor = genome["filter"]["neutral_anchor"]
    default_formants = {
        "F1": anchor.get("F1", {}).get("hz", 450) if isinstance(anchor.get("F1"), dict) else anchor.get("F1", 450),
        "F2": anchor.get("F2", {}).get("hz", 1500) if isinstance(anchor.get("F2"), dict) else anchor.get("F2", 1500),
        "F3": anchor.get("F3", {}).get("hz", 2770) if isinstance(anchor.get("F3"), dict) else anchor.get("F3", 2770),
        "F4": anchor.get("F4", {}).get("hz", 3100) if isinstance(anchor.get("F4"), dict) else anchor.get("F4", 3100),
    }
    default_bw = {"F1": 80, "F2": 100, "F3": 120, "F4": 150}

    # Fill formant tracks from segments
    for seg in plan.segments:
        if seg.kind == "silence":
            continue
        t0_sample = int(seg.t0 * SR)
        t1_sample = min(int(seg.t1 * SR), n_total)
        if t0_sample >= t1_sample:
            continue

        # Get formant targets
        targets = seg.targets if seg.targets else default_formants
        for f in ["F1", "F2", "F3", "F4"]:
            val = targets.get(f, default_formants[f])
            formant_tracks[f][t0_sample:t1_sample] = val
            bw_tracks[f][t0_sample:t1_sample] = default_bw[f]

        # Diphthong: interpolate between onset and offset
        if seg.kind == "diphthong" and seg.onset and seg.offset:
            grid = genome["vowel_grid"]
            if seg.onset in grid and seg.offset in grid:
                onset_f = grid[seg.onset]
                offset_f = grid[seg.offset]
                n_seg = t1_sample - t0_sample
                for fi, fk in enumerate(["F1", "F2", "F3"]):
                    vals = np.linspace(onset_f[fi], offset_f[fi] * seg.reach + onset_f[fi] * (1 - seg.reach), n_seg)
                    # Cosine easing
                    t_norm = np.arange(n_seg) / max(n_seg - 1, 1)
                    t_smooth = 0.5 * (1 - np.cos(np.pi * t_norm))
                    vals = onset_f[fi] + (offset_f[fi] - onset_f[fi]) * seg.reach * t_smooth
                    formant_tracks[fk][t0_sample:t1_sample] = vals

    # Fill gaps (between segments) with neutral
    for f in ["F1", "F2", "F3", "F4"]:
        # Forward fill
        last = default_formants[f]
        for i in range(n_total):
            if formant_tracks[f][i] == 0:
                formant_tracks[f][i] = last
            else:
                last = formant_tracks[f][i]
        # Backward fill leading zeros
        last = default_formants[f]
        for i in range(n_total - 1, -1, -1):
            if formant_tracks[f][i] == 0:
                formant_tracks[f][i] = last
            else:
                last = formant_tracks[f][i]

    # F0 track from anchors
    f0_base = 190.0 * effort_to_f0_shift(plan.style.effort)
    f0_track[:] = f0_base
    # Apply anchors (simplified: set F0 at anchor times)
    for anchor in plan.f0_anchors:
        t_sample = int(anchor.t * SR)
        if 0 <= t_sample < n_total:
            # Gaussian influence around anchor
            sigma = int(0.05 * SR)  # 50ms influence
            for i in range(max(0, t_sample - sigma), min(n_total, t_sample + sigma)):
                weight = np.exp(-((i - t_sample) / sigma) ** 2 / 2)
                f0_track[i] = f0_track[i] * (1 - weight) + anchor.value * weight

    # Rd track
    rd_base = effort_to_rd(plan.style.effort)
    rd_track[:] = rd_base

    # Generate source with phase accumulator
    source = np.zeros(n_total)
    phase_state = {"pos_in_cycle": 0.0}
    rng_src = np.random.default_rng(plan.style.seed)

    # Process in frames
    for frame_start in range(0, n_total, FRAME_SAMPLES):
        frame_end = min(frame_start + FRAME_SAMPLES, n_total)
        frame_len = frame_end - frame_start

        # Get current parameters (mid-frame)
        mid = frame_start + frame_len // 2
        f0_hz = f0_track[mid]
        rd = rd_track[mid]

        # Ensure f0 is in valid range
        f0_hz = max(75.0, min(600.0, f0_hz))

        # Generate source for this frame
        frame_source, phase_state = lf_source_frame(
            f0_hz, rd, frame_len, phase_state, SR, jitter_pct=0.7, rng=rng_src
        )
        source[frame_start:frame_end] = frame_source

    # Run resonators (per-formant, with state carry)
    output = np.zeros(n_total)
    resonator_state = {}  # {formant_name: zi}

    for frame_start in range(0, n_total, FRAME_SAMPLES):
        frame_end = min(frame_start + FRAME_SAMPLES, n_total)
        frame_len = frame_end - frame_start
        if frame_len == 0:
            break

        mid = frame_start + frame_len // 2

        # Get current formants and bandwidths
        frame_formants = {}
        frame_bw = {}
        for f in ["F1", "F2", "F3", "F4"]:
            frame_formants[f] = formant_tracks[f][mid]
            frame_bw[f] = bw_tracks[f][mid]

        # Process each formant
        for fname, f_freq in frame_formants.items():
            bw = frame_bw[fname]
            if bw <= 0:
                bw = 100.0
            if f_freq <= 0:
                continue

            b, a = resonator_coeffs(f_freq, bw, SR)

            # Get state
            zi = resonator_state.get(fname, None)
            if zi is None:
                zi = np.zeros(len(a) - 1)

            # Filter this frame's source
            frame_source = source[frame_start:frame_end]
            out, zi_new = lfilter(b, a, frame_source, zi=zi)
            resonator_state[fname] = zi_new

            output[frame_start:frame_end] += out

    # Radiation: +6 dB/oct high-freq boost (differentiator)
    output = np.diff(output, prepend=output[0])

    # Normalize
    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.5

    # Trim to actual duration
    output = output[:int(total_duration * SR)]

    return output


# ── Verification: compare to Phase 1 vowel ───────────────────────────────

def verify_vs_phase1(genome, vowel="ɑ", duration=1.0):
    """Render a single vowel and compare formants to Phase 1."""
    from phase1_synth import render_vowel, measure
    from synthetic_measure import measure_formants_synthetic, measure_f0_synthetic

    # Phase 1 render
    rng = np.random.default_rng(42)
    p1_signal = render_vowel(genome, vowel, 190.0, duration, "lf", rng)

    # Frame renderer: build a plan with one vowel
    grid = genome["vowel_grid"][vowel]
    anchor = genome["filter"]["neutral_anchor"]
    f4 = anchor["F4"]["hz"] if isinstance(anchor.get("F4"), dict) else anchor.get("F4", 3100)
    targets = {"F1": grid[0], "F2": grid[1], "F3": grid[2], "F4": f4}

    # Build a minimal plan
    plan = RenderPlan(text=vowel)
    plan.segments.append(Segment(
        i=0, phone=vowel, kind="vowel", t0=0.0, t1=duration,
        word=0, syll=0, stress=0, voiced=True, targets=targets,
    ))
    plan.style = Style(effort=0.5, seed=42)

    fr_signal = render_plan(plan, genome)

    # Measure both
    p1_f0 = measure_f0_synthetic(p1_signal, SR, target_f0=190.0)
    fr_f0 = measure_f0_synthetic(fr_signal, SR, target_f0=190.0)

    p1_formants = measure_formants_synthetic(p1_signal, SR, targets)
    fr_formants = measure_formants_synthetic(fr_signal, SR, targets)

    print(f"Verification: {vowel} ({duration}s)")
    print(f"  F0:  Phase1={p1_f0['median']:.1f}  FrameRenderer={fr_f0['median']:.1f}  Target=190.0")
    for f in ["F1", "F2", "F3", "F4"]:
        p1v = p1_formants[f]["median"]
        frv = fr_formants[f]["median"]
        tgt = targets[f]
        print(f"  {f}: Phase1={p1v:.0f}  FrameRenderer={frv:.0f}  Target={tgt}")

    return p1_signal, fr_signal


# ── Demo ─────────────────────────────────────────────────────────────────

def demo():
    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    genome = load_genome(genome_path)

    plan = build_plan("This is the moon.")
    audio = render_plan(plan, genome)

    out_path = os.path.join(os.path.dirname(__file__), "..", "renders", "phase4", "this_is_the_moon.wav")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    from scipy.io import wavfile
    wavfile.write(out_path, SR, (audio * 32767).astype(np.int16))
    print(f"Rendered: {out_path} ({len(audio)/SR:.2f}s)")

    # Also verify against Phase 1
    print("\n--- Verification vs Phase 1 ---")
    verify_vs_phase1(genome, "ɑ", 1.0)


def main():
    parser = argparse.ArgumentParser(description="VOICE frame renderer")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--text", type=str, default="This is the moon.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    genome = load_genome(genome_path)

    if args.demo:
        demo()
    elif args.verify:
        verify_vs_phase1(genome, "ɑ", 1.0)
    else:
        plan = build_plan(args.text)
        audio = render_plan(plan, genome)
        print(f"Rendered {len(audio)} samples ({len(audio)/SR:.2f}s)")
        if args.json:
            print(plan.to_json())


if __name__ == "__main__":
    main()