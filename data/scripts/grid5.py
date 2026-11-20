#!/usr/bin/env python3
"""Round 20/21 — band-relative mixed excitation on the cascade vowel.

Zarza r20: cascade builds the right envelope (/i/-/u/ F2 contrast 0.8 -> 23.1 dB)
but still 0/12, flatness 0.0 — a harmonic stack with a pretty envelope is not a
phoneme. Source-white aspiration can't penetrate the cascade (series resonators
reject it; /u/'s F3/F4 pass glottal noise into the high band, erasing contrast).

Hypothesis (the one untested lever): aperiodicity must be BAND-RELATIVE. Shape
noise by the vowel's own spectral envelope (cepstral smoothing separates the
formant envelope from the harmonic fine structure). A formant band gets filled
continuously; an empty band stays empty. /i/'s F2 becomes a real continuous peak
without flooding /u/'s high band. Judge on the isolation assay FIRST.

Usage: PYTHONPATH= /mnt/data/pocket-tts-venv/bin/python grid5.py <config>
"""
import sys, os, json, time
V = '/mnt/data/nar-r17/voice'
sys.path.insert(0, V + '/analysis')
import numpy as np, yaml
from scipy.signal import welch
from scipy.io import wavfile
from scipy.ndimage import gaussian_filter1d
import gate1_intelligibility as g1
import vowel_isolation_assay as assay
from cascade_vs_parallel import synthesize_parallel, synthesize_cascade
from phase1_synth import make_source

EXP = '/mnt/data/nar-r17'
WAVS = EXP + '/wavs'
os.makedirs(WAVS, exist_ok=True)
genome = yaml.safe_load(open(V + '/genome/voice_genome.yaml'))
anchor = genome['filter']['neutral_anchor']
BW = {k: anchor[k]['bw'] for k in ['F1', 'F2', 'F3', 'F4']}
VOWELS = assay.VOWELS
F0 = 190.0; DUR = 0.25; SR = 48000

CONFIGS = {
    'cascade':  dict(method='cascade'),
    'parallel': dict(method='parallel'),
    'mix6':     dict(method='cascade', hnr=6.0),
    'mix10':    dict(method='cascade', hnr=10.0),
    'mix14':    dict(method='cascade', hnr=14.0),
    'mix20':    dict(method='cascade', hnr=20.0),
    'pmix10':   dict(method='parallel', hnr=10.0),
    'mix10g':   dict(method='cascade', hnr=10.0, env='gauss'),
    'mix0':     dict(method='cascade', hnr=0.0),
    'mixn6':    dict(method='cascade', hnr=-6.0),
    'mixn6g':   dict(method='cascade', hnr=-6.0, env='gauss'),
}


def formants(vp):
    g = genome['vowel_grid'][vp]
    return {'F1': g[0], 'F2': g[1], 'F3': g[2], 'F4': anchor['F4']['hz']}


def cepstral_envelope(y, sr, f0):
    """Smooth spectral envelope via cepstral liftering below the pitch quefrency."""
    n = len(y)
    N = 1 << (n - 1).bit_length()
    spec = np.fft.rfft(y, n=N)
    logmag = np.log(np.abs(spec) + 1e-12)
    cep = np.fft.irfft(logmag, n=N)
    q = int(sr / f0)                      # pitch period in quefrency samples
    lifter = np.zeros(N)
    lifter[:q] = 1.0
    lifter[N - q + 1:] = 1.0
    env = np.exp(np.fft.rfft(cep * lifter, n=N))
    return env, N


def gauss_envelope(y, sr, f0):
    n = len(y)
    N = 1 << (n - 1).bit_length()
    spec = np.fft.rfft(y, n=N)
    logmag = np.log(np.abs(spec) + 1e-12)
    bin_hz = sr / N
    env = np.exp(gaussian_filter1d(logmag, 1.0 * f0 / bin_hz))
    return env, N


def mixed_excitation(y, hnr, env_kind='cepstral', seed=42):
    if env_kind == 'gauss':
        env, N = gauss_envelope(y, SR, F0)
    else:
        env, N = cepstral_envelope(y, SR, F0)
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, len(y))
    Noise = np.fft.rfft(noise, n=N)
    ns = np.fft.irfft(Noise * env, n=N)[:len(y)]
    sig_rms = float(np.sqrt(np.mean(y ** 2)))
    ns_rms = float(np.sqrt(np.mean(ns ** 2)))
    ns *= sig_rms * (10 ** (-hnr / 20.0)) / (ns_rms + 1e-12)
    return y + ns


def render_vowel(vp, cfg):
    rng = np.random.default_rng(42)
    src = make_source(genome, F0, DUR, 'lf', rng)
    fm = formants(vp)
    if cfg['method'] == 'parallel':
        y = synthesize_parallel(F0, fm, DUR, SR, src, bandwidths=BW)
    else:
        y = synthesize_cascade(F0, fm, DUR, SR, src, bandwidths=BW)
    if cfg.get('hnr') is not None:
        y = mixed_excitation(y, cfg['hnr'], cfg.get('env', 'cepstral'))
    return y


def f2band(y):
    f, P = welch(y[int(0.08*SR):int(0.2*SR)], fs=SR, nperseg=4096)
    return round(float(10*np.log10(P[(f >= 1800) & (f <= 2800)].sum()+1e-20)), 1)


def flatness(y):
    f, P = welch(y[int(0.08*SR):int(0.2*SR)], fs=SR, nperseg=4096)
    m = (f >= 100) & (f <= 8000)
    p = P[m] + 1e-20
    return round(float(np.exp(np.mean(np.log(p))) / np.mean(p)), 4)


def run(name):
    cfg = CONFIGS[name]
    t0 = time.time()
    paths, audio = [], {}
    for vp in VOWELS:
        y = render_vowel(vp, cfg)
        audio[vp] = y
        p = f'{WAVS}/{name}_{vp}.wav'
        wavfile.write(p, SR, (np.clip(y, -1, 1)*32767).astype('int16'))
        paths.append(p)
    hyps = g1.transcribe(paths)
    rows, npass = {}, 0
    for vp, h in zip(VOWELS, hyps):
        ok, vs = assay.iso_pass(vp, h)
        npass += ok
        rows[vp] = {'heard': h, 'pass': ok}
    rec = {
        'name': name, 'cfg': cfg,
        'iso_pass': npass, 'iso_total': len(VOWELS),
        'iso_i_heard': rows['i']['heard'], 'iso_i_pass': rows['i']['pass'],
        'iso_u_heard': rows['u']['heard'], 'iso_u_pass': rows['u']['pass'],
        'vowels': rows,
        'i_F2band': f2band(audio['i']), 'u_F2band': f2band(audio['u']),
        'contrast': round(f2band(audio['i']) - f2band(audio['u']), 1),
        'i_flat': flatness(audio['i']), 'u_flat': flatness(audio['u']),
        'render_s': round(time.time()-t0, 1),
    }
    rp = EXP + '/results5.json'
    results = json.load(open(rp)) if os.path.exists(rp) else []
    results = [r for r in results if r['name'] != name] + [rec]
    json.dump(results, open(rp, 'w'), indent=1, ensure_ascii=False)
    print(f"== {name} == iso {npass}/12  /i/->{rows['i']['heard']!r}({'P' if rows['i']['pass'] else '.'})  /u/->{rows['u']['heard']!r}({'P' if rows['u']['pass'] else '.'})")
    print(f"   F2 contrast {rec['contrast']}dB  i_flat {rec['i_flat']}  u_flat {rec['u_flat']}")
    print('   iso:', {vp: (r['heard'], 'P' if r['pass'] else '.') for vp, r in rows.items()})
    print(f"SAVED {rp} ({len(results)})")


if __name__ == '__main__':
    run(sys.argv[1])
