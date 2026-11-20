#!/usr/bin/env python3
"""Round 21 — mixed excitation re-tested on the VALID hVd floor.

The post-hoc envelope-noise test in grid5 used the bare-vowel assay, which is
invalid (natural speech fails it too). Re-test band-relative mixed excitation on
the hVd carrier frame so the intelligibility verdict means something. Apply
cepstral-envelope-shaped noise to the full render_plan_v3 word output, judge the
heard vowel category. Focus: does /i/ (heed) stop back-collapsing to "you"?

Usage: PYTHONPATH= /mnt/data/pocket-tts-venv/bin/python grid7.py <config>
"""
import sys, os, json, time
V = '/mnt/data/nar-r17/voice'
sys.path.insert(0, V + '/analysis')
sys.path.insert(0, '/mnt/data/nar-r17')
import numpy as np, yaml
from scipy.io import wavfile
from render_plan import build_plan, Style, SR
import prosody_poststage as pp
import gate1_intelligibility as g1
import vowel_isolation_assay as assay
from grid5 import mixed_excitation

EXP = '/mnt/data/nar-r17'
WAVS = EXP + '/wavs'
genome = yaml.safe_load(open(V + '/genome/voice_genome.yaml'))
HVD = assay.HVD

CONFIGS = {
    'hvd_base':  dict(),
    'hvd_mix10': dict(hnr=10.0),
    'hvd_mix6':  dict(hnr=6.0),
    'hvd_mix0':  dict(hnr=0.0),
    'hvd_mix10g': dict(hnr=10.0, env='gauss'),
}


def run(name):
    cfg = CONFIGS[name]
    t0 = time.time()
    paths, words, targets = [], [], []
    for w, vp in HVD:
        a = pp.render_plan_v3(build_plan(w, style=Style(seed=42)), genome)
        if cfg.get('hnr') is not None:
            a = mixed_excitation(a, cfg['hnr'], cfg.get('env', 'cepstral'))
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
    rp = EXP + '/results7.json'
    results = json.load(open(rp)) if os.path.exists(rp) else []
    results = [r for r in results if r['name'] != name] + [rec]
    json.dump(results, open(rp, 'w'), indent=1, ensure_ascii=False)
    print(f"== {name} == hVd {npass}/{len(words)}  heed/i/->{rows['heed']['heard']!r}({'P' if rows['heed']['pass'] else '.'})")
    print('   ', {w: (r['heard'], 'P' if r['pass'] else '.') for w, r in rows.items()})
    print(f"SAVED {rp}")


if __name__ == '__main__':
    run(sys.argv[1])
