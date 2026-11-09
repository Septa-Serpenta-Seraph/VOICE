#!/usr/bin/env python3
"""
VOICE — LF timing verification (Fant 1985 / Doval 2006)
========================================================
Verify the Rd → (Tp, Te, Ta) mapping against Fant, Liljencrants & Lin (1985).
The skeleton's approximation (te=0.6*T0, tp=0.45*te, ta=0.02*T0*rd/1.25)
is replaced with the Doval et al. (2006) re-parameterization, which is
a cleaner expression of the same Fant 1985 relationships.

Doval 2006 equations (from HAL science, JASA 2021):
  Ra = (1 + 4.8*Rd) / 100
  Rk = (22.4 + 11.8*Rd) / 100
  Rg = Rk*(0.5 + 1.2*Rk) / (0.44*Rd - 4*Ra*(0.5 + 1.2*Rk))
  Oq = (1 + Rk) / (2*Rg)          # open quotient = Te/T0
  am = 1 / (1 + Rk)               # asymmetry = Tp/Te
  Ta = Ra * T0                     # return phase time constant

  Te = Oq * T0                     # excitation time (end of open phase)
  Tp = am * Te                     # peak time
  T0 = 1/F0                        # period

Rd range: 0.4 (tense) to 2.7 (breathy). Genome default: 1.25 (modal-warm).

Verification checks:
  1. Timing parameters are positive and within valid ranges
  2. Te < T0 (open phase shorter than period)
  3. Tp < Te (peak before closing)
  4. Ta < Te (return phase shorter than open phase)
  5. Zero DC condition: integral of LF pulse over one period ≈ 0
  6. Value continuity at Te: opening phase value ≈ return phase value
  7. Rd sensitivity: higher Rd → higher Oq, higher Ta (breathier)
  8. Comparison with old approximation

Usage:
  python lf_timing_verify.py              # verify and print results
  python lf_timing_verify.py --sweep      # sweep Rd from 0.4 to 2.7
"""

import argparse
import json
import os
import sys

import numpy as np

SR = 48000


def lf_timing_doval(rd, f0):
    """Compute LF timing parameters from Rd using Doval 2006 / Fant 1985.

    Returns: (Tp, Te, Ta, T0, Oq, am, Ra, Rk, Rg) in seconds (except dimensionless).
    """
    t0 = 1.0 / f0

    # Doval 2006 re-parameterization
    ra = (1.0 + 4.8 * rd) / 100.0
    rk = (22.4 + 11.8 * rd) / 100.0
    rg = rk * (0.5 + 1.2 * rk) / (0.44 * rd - 4.0 * ra * (0.5 + 1.2 * rk))
    oq = (1.0 + rk) / (2.0 * rg)
    am = 1.0 / (1.0 + rk)

    te = oq * t0
    tp = am * te
    ta = ra * t0

    return {
        "Tp": tp, "Te": te, "Ta": ta, "T0": t0,
        "Oq": oq, "am": am, "Ra": ra, "Rk": rk, "Rg": rg,
        "rd": rd, "f0": f0,
    }


def lf_timing_old_approx(rd, f0):
    """Old skeleton approximation (for comparison)."""
    t0 = 1.0 / f0
    te = 0.60 * t0
    tp = 0.45 * te
    ta = 0.02 * t0 * (rd / 1.25)
    return {"Tp": tp, "Te": te, "Ta": ta, "T0": t0}


def compute_alpha(tp, te, ta, t0, sr):
    """Compute alpha for zero DC condition.

    Solve for alpha such that the integral of the LF pulse over one
    period is zero. Uses numerical root finding.

    The opening phase: E(t) = exp(α*t) * sin(ω*t), ω = π/Tp
    The return phase: E(t) = -A * [exp(-ε*(t-Te)) - exp(-ε*(T0-Te))]
    where A is chosen for value continuity at Te, ε = 1/Ta.

    Zero DC: ∫₀^Te E_open(t) dt + ∫_Te^T0 E_return(t) dt = 0
    """
    from scipy.optimize import brentq
    omega = np.pi / tp
    eps = 1.0 / ta

    # Value at Te from opening phase (without E0 scaling, since E0 cancels)
    # Return phase amplitude for continuity: A = exp(α*Te)*sin(ω*Te) / (1/(ε*Ta))*(1 - exp(-ε*(T0-Te)))
    # Actually, let's define the return phase as: -(E0/(ε*Ta)) * [exp(-ε*(t-Te)) - exp(-ε*(T0-Te))]
    # At Te: return value = -(E0/(ε*Ta)) * [1 - exp(-ε*(T0-Te))]
    # For continuity: exp(α*Te)*sin(ω*Te) = -(1/(ε*Ta)) * [1 - exp(-ε*(T0-Te))]
    # This determines E0 scaling, but α is free. We solve for α from zero DC.

    # Integral of opening phase: ∫₀^Te exp(α*t)*sin(ω*t) dt
    def integral_opening(alpha):
        # Analytical: [exp(α*Te)*(α*sin(ω*Te) - ω*cos(ω*Te)) + ω] / (α² + ω²)
        return (np.exp(alpha * te) * (alpha * np.sin(omega * te) - omega * np.cos(omega * te)) + omega) / (alpha**2 + omega**2)

    # Integral of return phase: ∫_Te^T0 -(1/(ε*Ta))*[exp(-ε*(t-Te)) - exp(-ε*(T0-Te))] dt
    # = -(1/(ε*Ta)) * [ (1-eps*... ) ... ]
    # Let's compute numerically
    def integral_return():
        t = np.linspace(te, t0, 1000)
        dt = t[1] - t[0]
        ret = -(1.0 / (eps * ta)) * (np.exp(-eps * (t - te)) - np.exp(-eps * (t0 - te)))
        return np.trapezoid(ret, t)

    ir = integral_return()

    # Zero DC: integral_opening(alpha) + ir = 0 (E0 cancels)
    def f(alpha):
        return integral_opening(alpha) + ir

    # Find root. Alpha is typically negative (damping).
    try:
        alpha = brentq(f, -5000, 5000, xtol=1e-10, maxiter=1000)
    except ValueError:
        # Try wider range
        try:
            alpha = brentq(f, -10000, 10000, xtol=1e-10, maxiter=1000)
        except ValueError:
            alpha = -omega / np.tan(omega * te) if abs(np.tan(omega * te)) > 1e-6 else 0.0

    return alpha, omega, eps


def lf_pulse_one_period(params, sr):
    """Generate one LF glottal flow derivative pulse.

    Returns the pulse array and diagnostic info.
    """
    rd = params["rd"]
    f0 = params["f0"]
    tp = params["Tp"]
    te = params["Te"]
    ta = params["Ta"]
    t0 = params["T0"]

    alpha, omega, eps = compute_alpha(tp, te, ta, t0, sr)
    e0 = 1.0

    n_samples = int(round(t0 * sr))
    t = np.arange(n_samples) / sr

    # Opening phase value at Te
    val_te_open = e0 * np.exp(alpha * te) * np.sin(omega * te)

    # Return phase amplitude for continuity: scale so return(Te) = val_te_open
    # return(Te) = -A * [1 - exp(-eps*(T0-Te))]
    # A = -val_te_open / [1 - exp(-eps*(T0-Te))]
    denom = 1.0 - np.exp(-eps * (t0 - te))
    if abs(denom) > 1e-10:
        A = -val_te_open / denom
    else:
        A = 0.0

    # Opening phase
    opening = np.where(
        t < te,
        e0 * np.exp(alpha * t) * np.sin(omega * t),
        0.0
    )
    # Return phase
    returning = np.where(
        (t >= te) & (t < t0),
        -A * (np.exp(-eps * (t - te)) - np.exp(-eps * (t0 - te))),
        0.0
    )
    pulse = opening + returning

    # Diagnostics
    idx_te = int(te * sr)
    if idx_te < n_samples and idx_te > 0:
        val_open = e0 * np.exp(alpha * te) * np.sin(omega * te)
        val_return = -A * (1.0 - np.exp(-eps * (t0 - te)))
        continuity_error = abs(val_open - val_return)
    else:
        continuity_error = float('inf')

    dc_integral = np.trapezoid(pulse, t)

    # Peak location in opening phase (should be within (0, Te))
    # Note: Tp is a shape parameter, not the exact peak time. The exponential
    # growth shifts the peak earlier than Tp. This is expected in the LF model.
    if idx_te > 0:
        peak_idx = np.argmax(np.abs(pulse[:idx_te]))
        peak_time = peak_idx / sr
    else:
        peak_time = 0.0

    # Check: peak is within open phase and not at the boundary
    peak_in_open_phase = 0 < peak_time < te

    return pulse, {
        "alpha": float(alpha),
        "omega": float(omega),
        "eps": float(eps),
        "A": float(A),
        "continuity_error": float(continuity_error),
        "dc_integral": float(dc_integral),
        "peak_time": float(peak_time),
        "peak_time_expected": float(tp),
        "peak_time_error": float(abs(peak_time - tp)),
        "peak_in_open_phase": bool(peak_in_open_phase),
    }


def verify_params(params):
    """Verify timing parameters are valid."""
    checks = []
    tp, te, ta, t0 = params["Tp"], params["Te"], params["Ta"], params["T0"]
    rd = params["rd"]

    checks.append(("Tp > 0", tp > 0))
    checks.append(("Te > 0", te > 0))
    checks.append(("Ta > 0", ta > 0))
    checks.append(("Te < T0 (open < period)", te < t0))
    checks.append(("Tp < Te (peak before close)", tp < te))
    checks.append(("Ta < Te (return < open)", ta < te))
    checks.append(("Oq in (0,1)", 0 < params["Oq"] < 1))
    checks.append(("am in (0,1)", 0 < params["am"] < 1))
    checks.append(("Rd in (0.4, 2.7)", 0.4 <= rd <= 2.7))

    return checks


def verify_pulse(params, sr=SR):
    """Verify the LF pulse (zero DC, continuity)."""
    pulse, diag = lf_pulse_one_period(params, sr)
    checks = []
    checks.append(("Value continuity at Te", diag["continuity_error"] < 1e-6))
    checks.append(("Zero DC (integral ≈ 0)", abs(diag["dc_integral"]) < 1e-3))
    checks.append(("Peak within open phase", diag["peak_in_open_phase"]))
    return checks, diag


def rd_sensitivity():
    """Verify Rd sensitivity: higher Rd → higher Oq, higher Ta."""
    results = []
    for rd in [0.4, 0.8, 1.25, 1.6, 2.0, 2.7]:
        params = lf_timing_doval(rd, 190.0)
        results.append({
            "rd": rd,
            "Oq": round(params["Oq"], 4),
            "am": round(params["am"], 4),
            "Tp_ms": round(params["Tp"] * 1000, 3),
            "Te_ms": round(params["Te"] * 1000, 3),
            "Ta_ms": round(params["Ta"] * 1000, 3),
        })

    # Check monotonicity
    oqs = [r["Oq"] for r in results]
    tas = [r["Ta_ms"] for r in results]
    oq_increasing = all(oqs[i] < oqs[i + 1] for i in range(len(oqs) - 1))
    ta_increasing = all(tas[i] < tas[i + 1] for i in range(len(tas) - 1))

    return results, oq_increasing, ta_increasing


def compare_old_vs_new(rd=1.25, f0=190.0):
    """Compare old approximation vs new Doval equations."""
    old = lf_timing_old_approx(rd, f0)
    new = lf_timing_doval(rd, f0)

    comparison = {}
    for key in ["Tp", "Te", "Ta"]:
        old_val = old[key]
        new_val = new[key]
        diff_pct = abs(new_val - old_val) / new_val * 100
        comparison[key] = {
            "old_ms": round(old_val * 1000, 3),
            "new_ms": round(new_val * 1000, 3),
            "diff_pct": round(diff_pct, 1),
        }

    return comparison


def main():
    parser = argparse.ArgumentParser(description="LF timing verification")
    parser.add_argument("--sweep", action="store_true",
                        help="Sweep Rd from 0.4 to 2.7")
    parser.add_argument("--rd", type=float, default=1.25,
                        help="Rd value to verify (default: 1.25)")
    parser.add_argument("--f0", type=float, default=190.0,
                        help="F0 in Hz (default: 190)")
    args = parser.parse_args()

    rd = args.rd
    f0 = args.f0

    print(f"LF Timing Verification — Fant 1985 / Doval 2006")
    print(f"  Rd = {rd}, F0 = {f0} Hz")
    print()

    # 1. Compute timing parameters
    params = lf_timing_doval(rd, f0)
    print("Timing parameters (Doval 2006):")
    print(f"  Tp = {params['Tp']*1000:.3f} ms (peak time)")
    print(f"  Te = {params['Te']*1000:.3f} ms (excitation time)")
    print(f"  Ta = {params['Ta']*1000:.3f} ms (return phase time constant)")
    print(f"  T0 = {params['T0']*1000:.3f} ms (period)")
    print(f"  Oq = {params['Oq']:.4f} (open quotient)")
    print(f"  am = {params['am']:.4f} (asymmetry)")
    print(f"  Ra = {params['Ra']:.4f}")
    print(f"  Rk = {params['Rk']:.4f}")
    print(f"  Rg = {params['Rg']:.4f}")
    print()

    # 2. Verify parameters
    param_checks = verify_params(params)
    print("Parameter validity:")
    all_pass = True
    for name, passed in param_checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  {name}: {status}")
    print()

    # 3. Verify pulse
    pulse_checks, diag = verify_pulse(params)
    print("Pulse verification:")
    for name, passed in pulse_checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  {name}: {status}")
    print(f"  alpha = {diag['alpha']:.1f}")
    print(f"  omega = {diag['omega']:.1f}")
    print(f"  eps = {diag['eps']:.1f}")
    print(f"  continuity_error = {diag['continuity_error']:.2e}")
    print(f"  dc_integral = {diag['dc_integral']:.2e}")
    print(f"  peak_time = {diag['peak_time']*1000:.3f} ms (expected {diag['peak_time_expected']*1000:.3f})")
    print()

    # 4. Compare with old approximation
    comparison = compare_old_vs_new(rd, f0)
    print("Old vs New (ms):")
    for key, vals in comparison.items():
        print(f"  {key}: old={vals['old_ms']}, new={vals['new_ms']}, "
              f"diff={vals['diff_pct']}%")
    print()

    # 5. Rd sensitivity
    sens_results, oq_increasing, ta_increasing = rd_sensitivity()
    print("Rd sensitivity (higher Rd = breathier):")
    print(f"  {'Rd':>6} {'Oq':>8} {'am':>8} {'Tp(ms)':>8} {'Te(ms)':>8} {'Ta(ms)':>8}")
    for r in sens_results:
        print(f"  {r['rd']:>6.2f} {r['Oq']:>8.4f} {r['am']:>8.4f} "
              f"{r['Tp_ms']:>8.3f} {r['Te_ms']:>8.3f} {r['Ta_ms']:>8.3f}")
    print(f"  Oq increasing with Rd: {'PASS' if oq_increasing else 'FAIL'}")
    print(f"  Ta increasing with Rd: {'PASS' if ta_increasing else 'FAIL'}")
    print()

    # Summary
    all_checks = param_checks + pulse_checks + [
        ("Oq increasing with Rd", oq_increasing),
        ("Ta increasing with Rd", ta_increasing),
    ]
    all_pass = all(c[1] for c in all_checks)
    print(f"Overall: {'ALL PASS' if all_pass else 'FAILURES'}")

    if args.sweep:
        print("\n" + "=" * 60)
        print("Rd sweep (0.4 to 2.7):")
        print(f"  {'Rd':>6} {'Oq':>8} {'am':>8} {'Tp(ms)':>8} {'Te(ms)':>8} {'Ta(ms)':>8}")
        for rd_val in np.arange(0.4, 2.71, 0.1):
            p = lf_timing_doval(rd_val, f0)
            print(f"  {rd_val:>6.2f} {p['Oq']:>8.4f} {p['am']:>8.4f} "
                  f"{p['Tp']*1000:>8.3f} {p['Te']*1000:>8.3f} {p['Ta']*1000:>8.3f}")

    # Save results
    out = os.path.join(os.path.dirname(__file__), "..", "renders",
                       "lf_timing_verification.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    results = {
        "rd": rd,
        "f0": f0,
        "params": {k: (v if not isinstance(v, (np.floating,)) else float(v))
                   for k, v in params.items()},
        "param_checks": {name: bool(passed) for name, passed in param_checks},
        "pulse_checks": {name: bool(passed) for name, passed in pulse_checks},
        "diagnostics": {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                        for k, v in diag.items()},
        "comparison_old_vs_new": comparison,
        "rd_sensitivity": sens_results,
        "oq_increasing": bool(oq_increasing),
        "ta_increasing": bool(ta_increasing),
        "overall_pass": bool(all_pass),
    }
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nReport: {out}")


if __name__ == "__main__":
    main()