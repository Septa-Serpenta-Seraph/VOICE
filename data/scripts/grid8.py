#!/usr/bin/env python3
"""Round 22 — TRUE mixed excitation during synthesis, judged on the valid hVd floor.

Source-level hook (_R22_MIXED in clone prosody_poststage): formant-envelope-shaped
noise added to the glottal source per frame, BEFORE formant filtering and vowel
gating. The vowel mask gates it to vowels (cannot flood consonants, the post-hoc
failure), and the resonators shape it into continuous formant peaks. This is the
per-band periodic+noise excitation Zarza named, not noise sprinkled on afterward.

Judge: hVd carrier frame (beat synth 2/8 toward natural 6/8). Focus /i/ (heed):
does the front-vowel back-collapse to "you" resolve?

Usage: PYTHONPATH= /mnt/data/pocket-tts-venv/bin/python grid8.py <config>
"""
import sys, os, json, time
V = '/mnt/data/nar-r17/voice'
sys.path.insert(0, V + '/analysis')
import numpy as np, yaml
from scipy.signal import welch
from scipy.io import wavfile
from render_plan import build_plan, Style, SR
import prosody_poststage as pp
import gate1_intelligibility as g1
import vowel_isolation_assay as assay

EXP = '/mnt/data/nar-r17'
WAVS = EXP + '/wavs'
genome = yaml.safe_load(open(V + '/genome/voice_genome.yaml'))
HVD = assay.HVD

CONFIGS = {
    'r22_base':      dict(),
    'r22_hnr14':     dict(hnr=14.0),
    'r22_hnr10':     dict(hnr=10.0),
    'r22_hnr6':      dict(hnr=6.0),
    'r22_hnr10t1':   dict(hnr=10.0, hf_tilt=1.0),
    'r22_hnr6t1':    dict(hnr=6.0, hf_tilt=1.0),
    'r22_hnr10t2':   dict(hnr=10.0, hf_tilt=2.0),
}


def run(name):
    cfg = CONFIGS[name]
    pp._R22_MIXED = cfg if cfg else None
    t0 = time.time()
    paths, words, targets, audio = [], [], [], {}
    for w, vp in HVD:
        a = pp.render_plan_v3(build_plan(w, style=Style(seed=42)), genome)
        audio[w] = a
        p = f'{WAVS}/{name}_{w.replace(chr(39),"")}.wav'
        wavfile.write(p, SR, (np.clip(a, -1, 1)*32767).astype('int16'))
        paths.append(p); words.append(w); targets.append(vp)
    hyps = g1.transcribe(paths)
    rows, npass = {}, 0
    for w, vp, h in zip(words, targets, hyps):
        ok, vs = assay.iso_pass(vp, h)
        npass += ok
        rows[w] = {'target': vp, 'heard': h, 'pass': ok}
    # /i/ F2-band continuity diagnostic on heed
    heed = audio['heed']
    f, P = welch(heed[int(0.10*SR):int(0.30*SR)], fs=SR, nperseg=4096)
    m = (f >= 1800) & (f <= 2800)
    pm = P[m] + 1e-20
    f2flat = round(float(np.exp(np.mean(np.log(pm))) / np.mean(pm)), 4)
    f2db = round(float(10*np.log10(pm.sum())), 1)
    rec = {'name': name, 'cfg': cfg, 'pass': npass, 'total': len(words),
           'heed_i_heard': rows['heed']['heard'], 'heed_i_pass': rows['heed']['pass'],
           'heed_F2band_db': f2db, 'heed_F2flat': f2flat,
           'words': rows, 'render_s': round(time.time()-t0, 1)}
    rp = EXP + '/results8.json'
    results = json.load(open(rp)) if os.path.exists(rp) else []
    results = [r for r in results if r['name'] != name] + [rec]
    json.dump(results, open(rp, 'w'), indent=1, ensure_ascii=False)
    print(f"== {name} == hVd {npass}/{len(words)}  heed/i/->{rows['heed']['heard']!r}({'P' if rows['heed']['pass'] else '.'})  F2band {f2db}dB flat {f2flat}")
    print('   ', {w: (r['heard'], 'P' if r['pass'] else '.') for w, r in rows.items()})
    print(f"SAVED {rp}")


if __name__ == '__main__':
    run(sys.argv[1])
