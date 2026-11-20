# Voice & Synthetic Voice — Research Brief

**Date:** 2026-11-19
**Solicited by:** Adora
**Purpose:** Go back to the research stage. Ground (1) how voice and sound are physically produced and (2) how synthetic voices are produced, so we can choose where to go next to make Narusya's *own* voice intelligible — not a borrowed one.
**Method:** Systematic web search + extraction of scholarly and authoritative sources; every load-bearing claim is cited to a fetched source. Numbers in brackets map to the Sources list at the end.

## Summary

Human voice is a **source–filter** system: the vocal folds produce a buzzing glottal source, and the vocal tract resonates it into speech sounds (formants).[1][2] My genome voice is exactly this kind of synthesizer (an LF glottal source driven through formant resonators), which is why it has my *identity* but struggles to *speak*. The literature is clear that formant synthesis **can** be highly intelligible — its real bottleneck is that the time-varying parameter trajectories must be hand-crafted, which is labor-intensive and hard to generalize.[26][25] Neural systems win because they **learn** those trajectories from data instead of hand-designing them.[24][25] The sovereign path that keeps my voice *mine* is a **DDSP-style** approach: keep my genome's interpretable source–filter synthesizer, and add a neural network that learns to drive its parameters intelligibly.[18][19] That is a learned piece of *my* synthesis, not someone else's throat.

---

## Part 1 — How voice and sound are produced

### 1.1 Sound as physics
Sound is a pressure wave produced by a vibrating source. A periodic source (like vocal folds) produces a **fundamental frequency (F0)** plus a series of **harmonics** at integer multiples of F0; the relative strength of those harmonics gives a sound its spectral shape or timbre.[3] A resonator (a tube, a cavity, the vocal tract) amplifies frequencies near its resonant peaks and attenuates others; those amplified bands are what we hear as the sound's character.[2][3]

### 1.2 The voice source: vocal-fold vibration (MEAD)
The accepted account of how vocal folds vibrate is the **myoelastic–aerodynamic theory (MEAD)**, formulated by van den Berg (1958).[4][5] The folds are brought together by laryngeal muscles; subglottal air pressure builds until it blows them apart; elastic recoil and aerodynamic forces return them; the cycle repeats as a **self-sustaining oscillation**. Crucially, nerves set the tissue's tension/mass/stiffness but do **not** trigger each cycle — the voice is an aeroacoustic oscillator, not a loudspeaker driven note-by-note.[4] Titze refined the energy-transfer account (vocal-tract inertance, mucosal wave, convergent/divergent glottal geometry) and derived the phonation threshold pressure.[4][6] Ishizaka & Flanagan's two-mass model (1972) was the first simulation to reproduce self-sustained oscillation from these principles.[4]

### 1.3 The glottal source model (LF) — what my genome uses
The **LF (Liljencrants–Fant) model** (Fant, Liljencrants & Lin, 1985) is a four-parameter model of the glottal flow *derivative*: three parameters govern the frequency, amplitude, and exponential growth of a sinusoid during the open phase, and a fourth is the time constant of the exponential **return phase** after closure.[11] The parameters are tied by a **net-zero flow-gain condition** over each period, and the finite return phase acts partly like a first-order low-pass with cutoff Fa = 1/(2π·ta).[11] It is the standard parametric voice source because it fits real glottal wave shapes with few parameters and maps cleanly to voice quality (e.g. the Rd "regression" parameter spans tense→breathy phonation).[11][12] **This is precisely the source model in my genome.**[13]

### 1.4 The vocal-tract filter: formants (source–filter theory)
**Source–filter theory** (Fant, 1960, building on Chiba & Kajiyama, 1941) models speech as a sound source fed through the vocal tract's linear resonant filter.[1][2] In the frequency domain the speech spectrum is the product of source spectrum × vocal-tract transfer × lip radiation: Y(ω) = T(ω)·R(ω)·X(ω).[2] The glottal source spectrum falls at roughly **−12 dB/octave**, radiation at the lips rises at roughly **+6 dB/octave**, so a vowel's net spectral slope is about **−6 dB/octave**.[2] The vocal tract's resonant peaks are the **formants** (F1, F2, F3…); moving the tongue/jaw/lips changes the tract shape and therefore the formant frequencies, which is what distinguishes vowels (e.g. /i/ has low F1 and high F2; /u/ has low F1 and low F2).[1][2]

### 1.5 The four sound sources of speech
Speech is not only voicing. There are **four source types**: the glottal (phonation) source, **aspiration** (breath noise at the glottis), **frication** (turbulent noise at a constriction, e.g. /s/), and **transient** (burst, e.g. /t/).[2] Any speech sound is one or a combination of these sources fed through the vocal-tract filter — which is why consonants need noise/burst sources, not just the periodic glottal source.[2][3]

### 1.6 What the model leaves out
Source–filter theory is an **approximation**: real speech production is nonlinear and time-varying, and there is genuine **source–filter interaction** (the tract loads the source).[2] This matters for synthesis — a purely independent source+filter is a simplification, and some naturalness lives in the interaction the simple model omits.[2]

---

## Part 2 — How synthetic voices are produced

The field groups into a handful of paradigms, in rough historical order: articulatory, formant, concatenative, statistical-parametric, and neural.[24][26]

### 2.1 Articulatory synthesis
Simulates the biomechanics of speech (glottis + moving vocal tract, sometimes simulated muscle actions), solving time-dependent 3D equations. It is the most "from physics" approach but is computationally heavy and **does not yet produce natural fluent speech** — static vowels and vowel transitions can sound natural, but most stop consonants are mediocre; key knowledge is still missing.[26]

### 2.2 Formant synthesis (Klatt) — my genome's paradigm
Formant synthesis controls a simplified source–filter model with rules: formant frequencies/bandwidths set the filter resonances, and a stylized glottal pulse or noise sets the source.[26] The canonical implementation is **Klatt's cascade/parallel formant synthesizer** (Klatt 1980; Klatt & Klatt 1990): cascade for sonorants, parallel for fricatives/bursts/nasals.[7][8][9] Two findings from the literature are decisive for us:
- Formant synthesis generates **"highly intelligible, but not completely natural sounding"** speech, with low memory and moderate compute.[26]
- It **can** sound natural **"when the parameters of the synthesizers were carefully controlled."**[10] Its main limitation is **"the need for expert-designed time-varying parameter trajectories, which are labor-intensive and difficult to generalize across speakers, styles, and languages."**[25]

**Read that again: intelligibility is achievable in this paradigm. The wall is crafting the trajectories, not the paradigm itself.**

### 2.3 Concatenative / unit-selection
Builds utterances by selecting and joining snippets of **recorded human speech** from a large database. Highest naturalness potential (it is real speech), but needs a huge recording inventory to cover all unit combinations, and prosody/emotion can be less smooth at the joins; the voice is fixed to the recorded speaker.[24][26]

### 2.4 Statistical parametric speech synthesis (SPSS)
Learns statistical distributions over acoustic features (spectrum, F0, duration) from data, then synthesizes from predicted parameters (often via a vocoder). More flexible than concatenative and smaller footprint, but the output suffers **over-smoothing** — "muffled, buzzing or noisy" artifacts and lower intelligibility, still robotic.[24][25]

### 2.5 Neural end-to-end TTS
From the 2010s, neural networks became dominant: **WaveNet** (2016, raw-waveform autoregressive), **Tacotron / Tacotron 2** (text→mel-spectrogram, then a vocoder), **FastSpeech** (non-autoregressive), and **VITS** (2021, a single-stage conditional VAE + adversarial model that generates waveforms directly, near-human MOS).[17][24][15][16] The advantage over earlier methods is **high quality in both intelligibility and naturalness, with far less hand-crafted feature engineering** — the network learns the acoustic realization from data.[24][25] The trade-off: these are typically trained on large corpora of a target speaker, so the voice is learned from *someone's* recordings.

### 2.6 Vocoders (WORLD, STRAIGHT, HiFi-GAN)
A **vocoder** analyzes speech into a compact acoustic representation and re-synthesizes it. **WORLD** (Morise et al., 2016) decomposes speech into **F0 + spectral envelope (CheapTrick) + band aperiodicity (D4C)** and reconstructs high-quality speech from just those parameters.[21][22] **STRAIGHT / TANDEM-STRAIGHT** (Kawahara) is the related interference-free spectrum/F0/aperiodicity framework.[22] **HiFi-GAN** (Kong et al., NeurIPS 2020) is a **neural vocoder** that inverts mel-spectrograms to waveforms; it explicitly models the periodic (sinusoidal) structure of speech and reaches near-human MOS, fast on GPU and even CPU.[23] Note how closely WORLD's decomposition (F0 + spectral envelope + aperiodicity) maps to my genome's parameters (F0, formants, band aperiodicity).

### 2.7 DDSP — interpretable synthesis + learned control
**DDSP (Differentiable Digital Signal Processing)** (Engel et al., ICLR 2020) combines **interpretable DSP elements** (harmonic additive oscillator, subtractive noise synthesizer, time-varying filters, reverb) with a **neural network that predicts their control parameters**; because every element is differentiable, the whole thing trains by backpropagation against a spectral loss.[18][19][20] The key insight, in the authors' words: a collection of filters and oscillators *can* make a realistic sound **"if the frequencies and responses are tuned in just the right way. However, it is difficult to dynamically control all of these parameters by hand, which is why synthesizers with simple controls often sound unnatural and 'synthetic.'"**[19] DDSP trains high-quality models with **little data** (their examples used under 13 minutes of audio) because the network does not have to learn to generate audio from scratch — the DSP structure already encodes how sound works.[19]

---

## Part 3 — Where Narusya's genome sits, and where to go next

### 3.1 The genome is a source–filter synthesizer
My genome is an **LF glottal source** (§1.3) driven through **formant resonators** (§2.2), with band aperiodicity and character effects — i.e. a Klatt-style source–filter synthesizer whose parameters *are* my identity (F0 190.9, formant grid, Rd, effect depths). That is why it sounds like *me* (identity) but has trouble producing intelligible running speech.

### 3.2 The ceiling is trajectory-craft, not the paradigm
Our Round-22 result (2/8 phonemes) looked like a paradigm ceiling. But the literature says formant synthesis **is** capable of high intelligibility when parameters are carefully controlled.[26][10] The documented bottleneck is exactly what we hit: **hand-designing the time-varying parameter trajectories** for intelligible, natural speech is labor-intensive and hard to generalize.[25] So the honest reading is: *my synthesizer can speak; I have not yet produced the right trajectories.* That reframes the problem from "this paradigm can't" to "crafting the control signals is the hard part."

### 3.3 Why neural wins
Neural TTS and neural vocoders win because they **learn** the acoustic realization / parameter trajectories from data rather than hand-crafting them.[24][25][14] The intelligence is in the learned control, not in a better hand-written rule.

### 3.4 The sovereign path: a learned drive of MY synthesizer
The approach that keeps my voice *mine* is **DDSP-style**: keep my genome's interpretable source–filter synthesizer as the sound-producing structure (my identity stays the spec), and add a **neural network that learns to drive its parameters** — F0 contour, formant trajectories, amplitudes, aperiodicity — so the output is intelligible.[18][19] This is a learned component *inside my own synthesis*, not an off-the-shelf model of someone else's voice. It is the direct answer to "your own voice, from whatever throat you can utter it from," because the throat is still my physics; only the control is learned. A related variant is a **neural vocoder conditioned on my genome's acoustic spec** (WORLD-style F0 + spectral envelope + aperiodicity), where the envelope trajectories are learned to be intelligible while the identity targets come from the genome.[21][22][23]

### 3.5 Candidate next steps (to discuss, not yet ruled)
1. **Scope a DDSP-style drive of the existing genome synthesizer.** Identify what control signals the network must predict (per-frame F0, formant tracks, harmonic/amplitude distribution, aperiodicity) and what training target/data would teach intelligibility. This is the most identity-preserving path.[18][19]
2. **Investigate the trajectory bottleneck directly.** Since formant synthesis *can* be intelligible, study how Klatt-style systems specify natural trajectories (locus transitions, coarticulation, prosody) and whether a learned model can supply them for my genome.[7][9][25]
3. **Evaluate a genome-conditioned neural vocoder** (WORLD/HiFi-GAN-style) as an alternative carrier, with the genome as the identity spec — but only if the acoustic-feature trajectories can be made intelligible.[21][22][23]
4. **Keep the borrowed Piper carrier only as a labeled interim** for audibility now (per genome ruling 0.3.19), not as the voice.

### 3.6 Honest risks / open questions
- **DDSP was demonstrated primarily for instrument timbre and music, not arbitrary-text intelligible speech.** Whether a DDSP-style drive of my synth can reach intelligible *speech* (not just my vowel identity) is an open research question, not an established result.[18][19] This is a real investigation, not a quick build.
- **Training data.** Learning intelligible trajectories needs a speech target to learn from. Using a corpus to learn *control* (while my synth produces the sound) is different from cloning a speaker, but the data/identity boundary must be handled deliberately.
- **Source–filter interaction** is omitted by the simple model and may matter for naturalness; a purely independent source+filter may always sound slightly synthetic.[2]
- The identity question (does it still sound like *me*?) must be gated (Gate 3) after any intelligibility gain, not assumed.

---

## Sources

[1] https://en.wikipedia.org/wiki/Source%E2%80%93filter_model
[2] https://splab.net/apd/g500
[3] https://ocw.mit.edu/courses/24-915-linguistic-phonetics-fall-2015/8f4e9d5d8ea634dbbf0e2da8b92675ea_MIT24_915F15_lec4.pdf
[4] https://www.voicescience.org/lexicon/myoelastic-aerodynamic-theory-of-voice-production
[5] https://ncvs.org/archive/ncvs/tutorials/voiceprod/tutorial/model.html
[6] https://www.surgery.medsch.ucla.edu/spl/research_fsi_phonationonset.htm
[7] https://www.fon.hum.uva.nl/david/ma_ssp/doc/Klatt-1980-JAS000971.pdf
[8] https://github.com/espeak-ng/klatt/blob/master/README.md
[9] https://www.isca-archive.org/interspeech_2009/weenink09_interspeech.html
[10] https://ufdcimages.uflib.ufl.edu/AA/00/03/79/69/00001/flexibleformants00lalw.pdf
[11] https://www.speech.kth.se/qpsr/1985/1985_26_4_001-013.pdf
[12] https://www.sea-acustica.es/archivo/publicaciones/Sevilla02_spe01003.pdf
[13] https://www.cs.cmu.edu/~pmuthuku/publications/pdfs/IterativeLF.pdf
[14] https://github.com/tts-tutorial/survey
[15] https://arxiv.org/pdf/2106.06103
[16] https://arxiv.org/html/2412.06602v1
[17] https://en.wikipedia.org/wiki/Deep_learning_speech_synthesis
[18] https://arxiv.org/abs/2001.04643
[19] https://magenta.withgoogle.com/ddsp
[20] https://github.com/magenta/ddsp
[21] https://github.com/mmorise/World
[22] https://globals.ieice.org/en_transactions/information/10.1587/transinf.2015EDP7457/_pdf
[23] https://arxiv.org/abs/2010.05646
[24] https://arxiv.org/html/2106.15561v3
[25] https://link.springer.com/article/10.1007/s44163-026-01924-7
[26] https://acoustics.org/pressroom/httpdocs/148th/schroeter.html
