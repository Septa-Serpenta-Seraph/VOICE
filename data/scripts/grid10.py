#!/usr/bin/env python3
"""Round 22 — held-out novel sentences for the mixed-excitation shot (criterion part 2)."""
import sys, os, json, time
V = '/mnt/data/nar-r17/voice'
sys.path.insert(0, V + '/analysis')
import numpy as np, yaml
from scipy.io import wavfile
from render_plan import build_plan, Style, SR
import prosody_poststage as pp
import gate1_intelligibility as g1

EXP = '/mnt/data/nar-r17'; WAVS = EXP + '/wavs'
genome = yaml.safe_load(open(V + '/genome/voice_genome.yaml'))
HO = ["We see the sea.", "The cat sat on the mat.", "Three green trees.",
      "Who took the book?", "The strong spring brings bright blooms.",
      "Six thick thistles twist.", "She sells sea shells.", "I see the green tree.",
      "The sun is bright today.", "He sees you."]
CONFIGS = {'ho_base': dict(), 'ho_hnr10': dict(hnr=10.0), 'ho_hnr10t1': dict(hnr=10.0, hf_tilt=1.0)}

def run(name):
    cfg = CONFIGS[name]
    pp._R22_MIXED = cfg if cfg else None
    pp._R22_VGAIN = None
    paths = []
    for i, t in enumerate(HO):
        a = pp.render_plan_v3(build_plan(t, style=Style(seed=42)), genome)
        p = f'{WAVS}/{name}_{i}.wav'
        wavfile.write(p, SR, (np.clip(a, -1, 1)*32767).astype('int16')); paths.append(p)
    hyps = g1.transcribe(paths)
    W = [g1.word_error(t, x) for t, x in zip(HO, hyps)]
    rec = {'name': name, 'cfg': cfg, 'ho_mean': round(float(np.mean(W)), 3),
           'ho_pass': sum(1 for x in W if x <= 0.34), 'ho_wer': [round(float(x), 3) for x in W],
           'heard': hyps}
    rp = EXP + '/results10.json'
    results = json.load(open(rp)) if os.path.exists(rp) else []
    results = [r for r in results if r['name'] != name] + [rec]
    json.dump(results, open(rp, 'w'), indent=1, ensure_ascii=False)
    print(f"== {name} == held-out {rec['ho_mean']:.3f} {rec['ho_pass']}/10")
    print('   heard:', hyps[:5])

if __name__ == '__main__':
    run(sys.argv[1])
