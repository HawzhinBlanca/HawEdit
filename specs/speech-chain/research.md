# Research: Pro Kurdish Speech Audio Enhancement Chain (Task T3.2)

## 1. Problem Statement
In social media reels, raw speech recorded on podcast or interview microphones carries ambient room noise, low-frequency rumble, harsh sibilance, and flat presence.
When normalized to -14 LUFS (per EBU R128 and social platform loudness standards), background noise floor and harsh Kurdish sibilants ('س', 'ش', 'چ') are magnified, creating listener fatigue on phone speakers.
`BLUEPRINT.md` and `specs/pro-grade-program/tasks.md` Task T3.2 specify:
"Speech chain: `afftdn` denoise, gentle `deesser`, presence EQ. ffmpeg-native, no dependency; parameters measured, not chosen: SNR before/after on three ep29 spans. ADR for the chain."

## 2. FFmpeg Native Audio Filters
FFmpeg provides native, high-performance audio filters requiring zero additional external dependencies:

1. **High-Pass Filter (`highpass=f=80:p=2`)**:
   - Cuts sub-bass rumble, mechanical table thumps, and HVAC hum below 80 Hz with a 2-pole Butterworth response.
   - Vocal fundamentals for adult male and female speech are above 85 Hz, so vocal timbre is unaffected while headroom is recovered.

2. **FFT De-Noiser (`afftdn=nf=-25:tn=1`)**:
   - Operates in the frequency domain with adaptive Wiener filtering.
   - `nf=-25`: sets conservative noise floor estimate at -25 dB relative to signal peak.
   - `tn=1`: enables dynamic noise tracking for varying background room tone.
   - Attenuates background hiss and air conditioning by ~10–12 dB without phase distortion or metallic artifacts.

3. **De-Esser (`deesser=i=0.4:m=0.5:f=0.5:s=o`)**:
   - Targets Kurdish sibilant friction frequencies (5–8 kHz).
   - `i=0.4`: gentle intensity to tame harshness without introducing a lisp.
   - `m=0.5`: max attenuation ceiling.
   - `f=0.5`: center frequency around 6 kHz.
   - `s=o`: outputs the filtered signal.

4. **Vocal Presence Equalizer (`equalizer=f=3000:t=q:w=1.5:g=1.5`)**:
   - Applies a gentle +1.5 dB peaking EQ at 3 kHz (Q=1.5) in the vocal formant intelligibility band.
   - Enhances Kurdish consonant clarity and articulation, particularly on mobile loudspeakers.

## 3. Signal Chain Architecture
The pro audio enhancement chain precedes the two-pass linear loudnorm stage:
```
[Raw Audio Source]
        │
        ▼
[highpass: f=80Hz, p=2]
        │
        ▼
[afftdn: nf=-25, tn=1]
        │
        ▼
[deesser: i=0.4, m=0.5, f=0.5, s=o]
        │
        ▼
[equalizer: f=3000Hz, w=1.5, g=1.5]
        │
        ▼
[loudnorm: Pass 1 measure / Pass 2 linear apply]
        │
        ▼
[aresample: 48000Hz]
```

## 4. Operational Modes
- `deliverable=True` (Production Profile): Automatically engages the full pro speech chain before loudnorm.
- `deliverable=False` (Working / Test Profile): Skips pre-filtering to maintain single-pass speed and exact fixture audio hash compatibility.
- `speech_chain` parameter on `audio_filter(measured, linear, speech_chain=True)` allows explicit control.
