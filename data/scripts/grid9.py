#!/usr/bin/env python3
"""Round 22 control — per-vowel F2 gain (correct direction) on the valid hVd floor.

Round 18 boosted /i/ F1 (wrong direction: /i/ needs F2 STRONG relative to F1).
The named defect is /i/ F2 weak -> back-collapse (heed->you). Boost /i/ F2 directly
and judge on hVd. This is the most direct attack on the named defect, untested on
the valid assay until now.

Usage: PYTHONPATH= /mnt/data/pocket-tts-venv/bin/python grid9.py <config>
"""
import sys, os, json, time
V = '/mnt/data/nar-r17/voice'
sys.path.insert(0, V + '/analysis')
import numpy as np, yaml
from scipy.io import wavfile
from render_plan import build_plan, Style, SR
import prosody_poststage as pp
import gate1_intelligibility as g1
import vowel_isolation_assay as assay

EXP = '/mnt/data/nar-r17'
WAVS = EXP + '/wavs'
genome = yaml.safe_load(open(V + '/genome/voice_genome.yaml'))
HVD = assay.HVD
I = 'i'; JI = '\u026a'; UH = '\u028a'

CONFIGS = {
    'vg_base':    dict(),
    'vg_i2':      dict(vgain={I: {'F2': 2.0}}),
    'vg_i4':      dict(vgain={I: {'F2': 4.0}}),
    'vg_i8':      dict(vgain={I: {'F2': 8.0}}),
    'vg_i4f1cut': dict(vgain={I: {'F2': 4.0, 'F1': 0.5}}),
    'vg_close':   dict(vgain={I: {'F2': 4.0}, JI: {'F2': 2.0}, UH: {'F2': 2.0}}),
}


def run(name):
    cfg = CONFIGS[name]
    pp._R22_MIXED = None
    pp._R22_VGAIN = cfg.get('vgain')
    t0 = time.time()
    paths, words, targets = [], [], []
    for w, vp in HVD:
        a = pp.render_plan_v3(build_plan(w, style=Style(seed=42)), genome)
        p = f'{WAVS}/{name}_{w.replace(chr(39),"")}.wav'
        wavfile.write(p, SR, (np.clip(a, -1, 1)*32767).astype('int16'))
        paths.append(p); words.append(w); targets.append(vp)
    hyps = g1.transcribe(paths)
    rows, npass = {}, 0
    for w, vp, h in zip(words, targets, hyps):
        ok, vs = assay.iso_pass(vp, h)
        npass += ok
        rows[w] = {'target': vp, 'heard': h, 'pass': ok}
    rec = {'name': name, 'cfg': cfg, 'pass': npass, 'total': len(words),
           'heed_i_heard': rows['heed']['heard'], 'heed_i_pass': rows['heed']['pass'],
           'words': rows, 'render_s': round(time.time()-t0, 1)}
    rp = EXP + '/results9.json'
    results = json.load(open(rp)) if os.path.exists(rp) else []
    results = [r for r in results if r['name'] != name] + [rec]
    json.dump(results, open(rp, 'w'), indent=1, ensure_ascii=False)
    print(f"== {name} == hVd {npass}/{len(words)}  heed/i/->{rows['heed']['heard']!r}({'P' if rows['heed']['pass'] else '.'})")
    print('   ', {w: (r['heard'], 'P' if r['pass'] else '.') for w, r in rows.items()})
    print(f"SAVED {rp}")


if __name__ == '__main__':
    run(sys.argv[1])
