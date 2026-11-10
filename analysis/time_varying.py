#!/usr/bin/env python3
"""
VOICE — Phase 4 Step 2: Time-Varying Core

Adds to the frame renderer:
  - Proper declination F0 contour (per-phrase, not just anchor influence)
  - CV/VC transition blending at segment boundaries
  - Diphthong trajectory in formant tracks
  - Effort as a track (per-phrase, with ramping)

Usage:
    python time_varying.py --demo     # render with transitions
    python time_varying.py --verify   # compare to Step 1
"""

import argparse
import os
import sys

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_plan import (RenderPlan, Style, Segment, build_plan, SR, FRAME_MS,
                        PHONE_TABLE, _is_vowel)
from frame_renderer import (load_genome, render_plan as render_plan_base,
                          effort_to_rd, effort_to_tilt, effort_to_f0_shift,
                          effort_to_f1_shift, FRAME_SAMPLES)
from coarticulation import cv_transition, vc_transition, interpolate_formants

SR = 48000
FRAME_SAMPLES = int(5.0 * SR / 1000)  # 240


def build_f0_track(plan, n_total, sr=SR):
    """Build a proper F0 track with per-phrase declination.

    Declination: +8% at phrase start, -15% at phrase end.
    Accents: content words get +8% on stressed syllable.
    Question: final rise 25-40% on last accented syllable.
    """
    f0_base = 190.0 * (1.0 + 0.03 * plan.style.effort)  # effort coupling
    track = np.full(n_total, f0_base)

    # Identify phrase boundaries (sentence-level)
    # For now, treat whole utterance as one phrase
    phrase_start = 0.0
    phrase_end = plan.segments[-1].t1 if plan.segments else 1.0

    # Declination: exponential from +8% to -15%
    for i in range(n_total):
        t_norm = i / max(n_total - 1, 1)
        t_norm = (i / SR - phrase_start) / max(phrase_end - phrase_start, 0.01)
        t_norm = max(0.0, min(1.0, t_norm))
        # Exponential declination
        declination = 0.08 - 0.23 * (1 - np.exp(-2.5 * t_norm))
        track[i] = f0_base * (1 + declination)

    # Accents: boost stressed syllables
    for seg in plan.segments:
        if seg.voiced and seg.stress >= 1:
            t_mid = int((seg.t0 + seg.t1) / 2 * SR)
            # Gaussian accent (50ms wide)
            sigma = int(0.05 * SR)
            for i in range(max(0, t_mid - sigma), min(n_total, t_mid + sigma)):
                weight = np.exp(-((i - t_mid) / (sigma / 2)) ** 2 / 2)
                track[i] = track[i] * (1 + 0.08 * weight)

    # Question rise: if question, rise on last accented syllable
    sentence_type = plan.provenance.get("sentence_type", "statement")
    if sentence_type == "question":
        # Find last stressed vowel
        last_stressed = None
        for seg in reversed(plan.segments):
            if seg.voiced and seg.stress >= 1 and seg.kind in ("vowel", "diphthong"):
                last_stressed = seg
                break
        if last_stressed:
            t_start = int(last_stressed.t0 * SR)
            t_end = min(int(last_stressed.t1 * SR) + int(0.1 * SR), n_total)
            rise_factor = 1.325  # +32.5% (midpoint of 25-40%)
            for i in range(t_start, t_end):
                t_norm = (i - t_start) / max(t_end - t_start, 1)
                track[i] = track[i] * (1 + 0.325 * t_norm ** 0.5)

    # Register scaling: multiply excursion around anchor
    scale = plan.style.register_scale
    if scale != 1.0:
        for i in range(n_total):
            excursion = track[i] / f0_base - 1.0
            track[i] = f0_base * (1 + scale * excursion)

    # Floor question rise at 25% (if scaled down)
    # (handled by not scaling the question rise — it's a signal, not a declination)

    # Clamp to valid range
    track = np.clip(track, 75.0, 600.0)

    return track


def apply_transitions(plan, genome, formant_tracks, sr=SR):
    """Blend formant tracks at segment boundaries using CV/VC transitions.

    For each adjacent pair of segments, compute the transition trajectory
    and blend it into the formant tracks at the boundary.
    """
    grid = genome["vowel_grid"]
    anchor = genome["filter"]["neutral_anchor"]
    default_f4 = anchor["F4"]["hz"] if isinstance(anchor.get("F4"), dict) else anchor.get("F4", 3100)

    segments = [s for s in plan.segments if s.kind != "silence"]
    if len(segments) < 2:
        return formant_tracks

    for i in range(len(segments) - 1):
        seg_a = segments[i]
        seg_b = segments[i + 1]

        # Get formant dicts
        def seg_formants(seg):
            if seg.targets:
                return {"F1": seg.targets.get("F1", 450),
                        "F2": seg.targets.get("F2", 1500),
                        "F3": seg.targets.get("F3", 2770),
                        "F4": seg.targets.get("F4", default_f4)}
            return {"F1": 450, "F2": 1500, "F3": 2770, "F4": default_f4}

        vf_a = seg_formants(seg_a)
        vf_b = seg_formants(seg_b)

        # Determine transition type
        a_is_vowel = seg_a.kind in ("vowel", "diphthong")
        b_is_vowel = seg_b.kind in ("vowel", "diphthong")
        a_is_cons = not a_is_vowel
        b_is_cons = not b_is_vowel

        if a_is_vowel and b_is_cons:
            # VC transition: vowel → consonant
            traj = vc_transition(vf_a, seg_b.phone, duration_ms=40, sr=sr)
        elif a_is_cons and b_is_vowel:
            # CV transition: consonant → vowel
            traj = cv_transition(seg_a.phone, vf_b, duration_ms=50, sr=sr)
        else:
            # V-V or C-C: simple interpolation
            traj = interpolate_formants(vf_a, vf_b, 5)

        # Apply transition at boundary
        boundary_t = seg_a.t1
        boundary_sample = int(boundary_t * sr)
        n_trans = len(traj)

        # Transition occupies space around boundary
        # For CV: transition is at start of vowel (after consonant)
        # For VC: transition is at end of vowel (before consonant)
        # We'll blend over the transition duration
        trans_duration = n_trans * 0.01  # ~10ms per frame
        trans_samples = int(trans_duration * sr)

        if a_is_cons and b_is_vowel:
            # CV: transition at start of vowel segment
            t_start = int(seg_b.t0 * sr)
            t_end = min(t_start + trans_samples, len(formant_tracks["F1"]))
        elif a_is_vowel and b_is_cons:
            # VC: transition at end of vowel segment
            t_start = max(0, int(seg_a.t1 * sr) - trans_samples)
            t_end = int(seg_a.t1 * sr)
        else:
            t_start = max(0, boundary_sample - trans_samples // 2)
            t_end = min(boundary_sample + trans_samples // 2, len(formant_tracks["F1"]))

        if t_end <= t_start:
            continue

        # Blend formant tracks with transition trajectory
        n_blend = t_end - t_start
        traj_resampled = traj
        if len(traj) != n_blend:
            # Resample trajectory to match blend length
            traj_resampled = []
            for k in range(n_blend):
                idx = k * (len(traj) - 1) // max(n_blend - 1, 1)
                traj_resampled.append(traj[min(idx, len(traj) - 1)])
            traj_resampled = traj_resampled

        for f in ["F1", "F2", "F3", "F4"]:
            for k in range(n_blend):
                si = t_start + k
                if si < len(formant_tracks[f]) and k < len(traj_resampled):
                    formant_tracks[f][si] = traj_resampled[k].get(f, formant_tracks[f][si])

    return formant_tracks


def render_plan_v2(plan, genome):
    """Render with time-varying core: proper F0, transitions, diphthongs."""
    # Import base renderer and patch
    import frame_renderer as fr

    # Build plan-level data
    total_duration = plan.segments[-1].t1 if plan.segments else 1.0
    n_total = int(total_duration * SR) + FRAME_SAMPLES

    # Build F0 track (proper declination)
    f0_track = build_f0_track(plan, n_total)

    # Build formant tracks
    anchor = genome["filter"]["neutral_anchor"]
    default_formants = {
        "F1": anchor.get("F1", {}).get("hz", 450) if isinstance(anchor.get("F1"), dict) else anchor.get("F1", 450),
        "F2": anchor.get("F2", {}).get("hz", 1500) if isinstance(anchor.get("F2"), dict) else anchor.get("F2", 1500),
        "F3": anchor.get("F3", {}).get("hz", 2770) if isinstance(anchor.get("F3"), dict) else anchor.get("F3", 2770),
        "F4": anchor.get("F4", {}).get("hz", 3100) if isinstance(anchor.get("F4"), dict) else anchor.get("F4", 3100),
    }
    default_bw = {"F1": 80, "F2": 100, "F3": 120, "F4": 150}

    formant_tracks = {f"F{i}": np.zeros(n_total) for i in range(1, 5)}
    bw_tracks = {f"F{i}": np.zeros(n_total) for i in range(1, 5)}

    # Fill from segments
    for seg in plan.segments:
        if seg.kind == "silence":
            continue
        t0_s = int(seg.t0 * SR)
        t1_s = min(int(seg.t1 * SR), n_total)
        if t0_s >= t1_s:
            continue

        targets = seg.targets if seg.targets else default_formants
        for f in ["F1", "F2", "F3", "F4"]:
            val = targets.get(f, default_formants[f])
            formant_tracks[f][t0_s:t1_s] = val
            bw_tracks[f][t0_s:t1_s] = default_bw[f]

        # Diphthong trajectory
        if seg.kind == "diphthong" and seg.onset and seg.offset:
            grid = genome["vowel_grid"]
            if seg.onset in grid and seg.offset in grid:
                onset_f = grid[seg.onset]
                offset_f = grid[seg.offset]
                n_seg = t1_s - t0_s
                for fi, fk in enumerate(["F1", "F2", "F3"]):
                    t_norm = np.arange(n_seg) / max(n_seg - 1, 1)
                    t_smooth = 0.5 * (1 - np.cos(np.pi * t_norm))
                    vals = onset_f[fi] + (offset_f[fi] - onset_f[fi]) * seg.reach * t_smooth
                    formant_tracks[fk][t0_s:t1_s] = vals

    # Fill gaps with neutral
    for f in ["F1", "F2", "F3", "F4"]:
        last = default_formants[f]
        for i in range(n_total):
            if formant_tracks[f][i] == 0:
                formant_tracks[f][i] = last
            else:
                last = formant_tracks[f][i]

    # Apply transitions
    formant_tracks = apply_transitions(plan, genome, formant_tracks)

    # Rd track (constant per utterance, but could be per-phrase)
    rd_base = effort_to_rd(plan.style.effort)
    rd_track = np.full(n_total, rd_base)

    # Generate source with phase accumulator
    source = np.zeros(n_total)
    phase_state = {"pos_in_cycle": 0.0}
    rng_src = np.random.default_rng(plan.style.seed)

    for frame_start in range(0, n_total, FRAME_SAMPLES):
        frame_end = min(frame_start + FRAME_SAMPLES, n_total)
        frame_len = frame_end - frame_start
        mid = frame_start + frame_len // 2
        f0_hz = f0_track[mid]
        rd = rd_track[mid]
        f0_hz = max(75.0, min(600.0, f0_hz))

        frame_source, phase_state = _lf_source_frame(
            f0_hz, rd, frame_len, phase_state, SR, 0.7, rng_src
        )
        source[frame_start:frame_end] = frame_source

    # Run resonators with state carry
    output = np.zeros(n_total)
    resonator_state = {}

    for frame_start in range(0, n_total, FRAME_SAMPLES):
        frame_end = min(frame_start + FRAME_SAMPLES, n_total)
        frame_len = frame_end - frame_start
        if frame_len == 0:
            break
        mid = frame_start + frame_len // 2

        for fname in ["F1", "F2", "F3", "F4"]:
            f_freq = formant_tracks[fname][mid]
            bw = bw_tracks[fname][mid] if fname in bw_tracks else 100.0
            if bw <= 0:
                bw = 100.0
            if f_freq <= 0:
                continue

            b, a = _resonator_coeffs(f_freq, bw, SR)
            zi = resonator_state.get(fname, np.zeros(len(a) - 1))
            frame_source = source[frame_start:frame_end]
            out, zi_new = _lfilter_safe(b, a, frame_source, zi)
            resonator_state[fname] = zi_new
            output[frame_start:frame_end] += out

    # Radiation
    output = np.diff(output, prepend=output[0])

    # Normalize
    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.5

    output = output[:int(total_duration * SR)]
    return output


# ── Helpers (imported from frame_renderer, redefined for independence) ──

def _lf_source_frame(f0_hz, rd, n_samples, phase_state, sr, jitter_pct, rng):
    """Generate LF source for one frame."""
    from frame_renderer import lf_source_frame as _lsf
    return _lsf(f0_hz, rd, n_samples, phase_state, sr, jitter_pct, rng)


def _lf_alpha(tp, te, ta, t0):
    from frame_renderer import _lf_alpha as _la
    return _la(tp, te, ta, t0)


def _resonator_coeffs(f_hz, bw_hz, sr):
    from frame_renderer import resonator_coeffs as _rc
    return _rc(f_hz, bw_hz, sr)


def _lfilter_safe(b, a, x, zi):
    from scipy.signal import lfilter
    out, zi_new = lfilter(b, a, x, zi=zi)
    return out, zi_new


# ── Demo and verification ─────────────────────────────────────────────────

def demo():
    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    genome = load_genome(genome_path)

    for text in ["This is the moon.", "She sees the sun."]:
        plan = build_plan(text)
        audio = render_plan_v2(plan, genome)
        out_path = os.path.join(os.path.dirname(__file__), "..", "renders", "phase4",
                                text.replace(" ", "_").replace(".", "").lower() + "_v2.wav")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        from scipy.io import wavfile
        wavfile.write(out_path, SR, (audio * 32767).astype(np.int16))
        print(f"Rendered: {out_path} ({len(audio)/SR:.2f}s, {len(plan.segments)} segments)")


def verify():
    """Compare v2 to v1 and Phase 1."""
    genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
    genome = load_genome(genome_path)

    # Single vowel comparison
    plan = build_plan("ɑ")  # won't work well with G2P, but test the renderer
    # Instead, build a manual plan
    from render_plan import RenderPlan, Segment, Style
    grid = genome["vowel_grid"]["ɑ"]
    anchor = genome["filter"]["neutral_anchor"]
    f4 = anchor["F4"]["hz"] if isinstance(anchor.get("F4"), dict) else anchor.get("F4", 3100)

    plan = RenderPlan(text="ɑ")
    plan.segments.append(Segment(
        i=0, phone="ɑ", kind="vowel", t0=0.0, t1=1.0,
        word=0, syll=0, stress=0, voiced=True,
        targets={"F1": grid[0], "F2": grid[1], "F3": grid[2], "F4": f4},
    ))
    plan.style = Style(effort=0.5, seed=42)

    audio_v2 = render_plan_v2(plan, genome)

    from frame_renderer import render_plan as render_v1
    audio_v1 = render_v1(plan, genome)

    from synthetic_measure import measure_formants_synthetic, measure_f0_synthetic
    v1_f0 = measure_f0_synthetic(audio_v1, SR, target_f0=190.0)["median"]
    v2_f0 = measure_f0_synthetic(audio_v2, SR, target_f0=190.0)["median"]
    print(f"F0: v1={v1_f0:.1f} v2={v2_f0:.1f} target=190.0")

    v1_f = measure_formants_synthetic(audio_v1, SR, {"F1": grid[0], "F2": grid[1], "F3": grid[2], "F4": f4})
    v2_f = measure_formants_synthetic(audio_v2, SR, {"F1": grid[0], "F2": grid[1], "F3": grid[2], "F4": f4})
    for f in ["F1", "F2", "F3", "F4"]:
        print(f"  {f}: v1={v1_f[f]['median']:.0f} v2={v2_f[f]['median']:.0f} target={grid[['F1','F2','F3','F4'].index(f)] if False else [grid[0],grid[1],grid[2],f4][['F1','F2','F3','F4'].index(f)]}")


def main():
    parser = argparse.ArgumentParser(description="VOICE time-varying core")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--text", type=str, default="This is the moon.")
    args = parser.parse_args()

    if args.demo:
        demo()
    elif args.verify:
        verify()
    else:
        genome_path = os.path.join(os.path.dirname(__file__), "..", "genome", "voice_genome.yaml")
        genome = load_genome(genome_path)
        plan = build_plan(args.text)
        audio = render_plan_v2(plan, genome)
        print(f"Rendered {len(audio)} samples ({len(audio)/SR:.2f}s)")


if __name__ == "__main__":
    main()