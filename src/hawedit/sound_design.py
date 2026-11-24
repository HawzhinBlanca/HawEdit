"""Procedural cinema micro-SFX synthesis for short-form editorial polish (D-376).

Synthesizes ultra-subtle, copyright-free broadcast audio textures using only the Python
standard library (`array`, `math`, `wave`):

1. Opening hook velvet sub-thump (0 ms, 300 ms): warm 92 Hz -> 44 Hz pitch drop at -23 dBFS
   giving the frame-0 hook card tactile broadcast presence without muddying voice.
2. Jump-cut airy whooshes (max 6 per reel, >= 5.0 s spacing): soft 180 ms Hann-windowed
   low-pass noise breeze sweeping 180 -> 720 -> 220 Hz at -26 dBFS centered on A/B cuts.

Mixed softly under dialogue via `amix=normalize=0` prior to two-pass linear `-14.0 LUFS`
loudnorm so speech loudness and true-peak ceilings remain strictly within broadcast spec.
"""

from __future__ import annotations

import array
import math
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Final, Literal

__all__ = [
    "DEFAULT_SFX_SAMPLE_RATE",
    "MusicMood",
    "select_sfx_transitions_ms",
    "write_cinema_sfx_wav",
]

MusicMood = Literal["none", "curious", "cinematic", "energetic"]
DEFAULT_SFX_SAMPLE_RATE: Final[int] = 48_000
_HOOK_THUMP_GAIN: Final[float] = 0.070  # ~ -23 dBFS
_WHOOSH_GAIN: Final[float] = 0.050  # ~ -26 dBFS
_AMBIENT_BASE_GAIN: Final[float] = 0.036  # ~ -29 dBFS unducked (subtle dark-studio bed)
_AMBIENT_DUCK_FACTOR: Final[float] = 0.42  # ~ -7.5 dB extra ducking under active speech
_TWO_PI: Final[float] = 2.0 * math.pi

# Warm studio harmonic chord tables (Hz) for 100% copyright-free procedural CC0 ambient beds.
_MOOD_CHORDS_HZ: Final[dict[str, tuple[tuple[float, ...], ...]]] = {
    "curious": (
        (110.0, 164.81, 220.0, 261.63),  # A minor 7 warm pad
        (87.31, 130.81, 174.61, 220.0),  # F major 7
        (98.00, 146.83, 196.0, 246.94),  # G6
        (110.0, 164.81, 220.0, 293.66),  # A sus4
    ),
    "cinematic": (
        (73.42, 110.0, 146.83, 174.61),  # D minor deep studio pad
        (87.31, 130.81, 174.61, 220.0),  # F major
        (65.41, 98.00, 130.81, 196.0),  # C5 open
        (82.41, 123.47, 164.81, 196.0),  # E minor
    ),
    "energetic": (
        (130.81, 196.0, 261.63, 329.63),  # C major bright pulse
        (146.83, 220.0, 293.66, 349.23),  # D minor 7
        (110.0, 164.81, 220.0, 261.63),  # A minor
        (98.00, 146.83, 196.0, 246.94),  # G major
    ),
}


def select_sfx_transitions_ms(
    jump_cuts_ms: Sequence[int],
    duration_ms: int,
    *,
    min_spacing_ms: int = 5_000,
    max_count: int = 6,
) -> tuple[int, ...]:
    """Select well-spaced jump-cut timestamps for tasteful airy transition whooshes."""
    if duration_ms < 4_000 or max_count <= 0:
        return ()
    selected: list[int] = []
    min_t = 2_000
    max_t = duration_ms - 1_500
    for t in sorted(int(x) for x in jump_cuts_ms):
        if t < min_t or t > max_t:
            continue
        if selected and (t - selected[-1]) < min_spacing_ms:
            continue
        selected.append(t)
        if len(selected) >= max_count:
            break
    return tuple(selected)


def write_cinema_sfx_wav(
    path: Path,
    duration_ms: int,
    *,
    transition_ms: Sequence[int] = (),
    pop_ms: Sequence[int] = (),
    riser_ms: Sequence[int] = (),
    sample_rate: int = DEFAULT_SFX_SAMPLE_RATE,
    include_hook_thump: bool = True,
    music_mood: MusicMood = "none",
    speech_intervals_ms: Sequence[tuple[int, int]] = (),
) -> Path:
    """Write a deterministic 16-bit mono PCM WAV bed of subtle cinema micro-SFX & CC0 music pad."""
    if duration_ms <= 0:
        raise ValueError(f"duration_ms must be positive, got {duration_ms}")
    if sample_rate <= 0:
        raise ValueError(f"sample_rate must be positive, got {sample_rate}")
    if music_mood not in ("none", "curious", "cinematic", "energetic"):
        raise ValueError(f"Unsupported music_mood: {music_mood!r}")

    total_samples = max(1, round(duration_ms * sample_rate / 1000.0))
    buf = array.array("f", [0.0]) * total_samples

    # 0. Optional subtle CC0 warm Rhodes-like ambient music pad, auto-ducked under speech.
    if music_mood != "none":
        chords = _MOOD_CHORDS_HZ[music_mood]
        bar_s = 4.0 if music_mood != "energetic" else 2.5
        bar_n = max(1, round(bar_s * sample_rate))
        # Build 20 ms speech-ducking envelope for silky automatic voice ducking.
        duck_step = max(1, sample_rate // 50)
        n_blocks = (total_samples + duck_step - 1) // duck_step
        duck_env = [1.0] * n_blocks
        for sp_s, sp_e in speech_intervals_ms:
            b0 = max(0, int(sp_s * 50 // 1000))
            b1 = min(n_blocks, int(sp_e * 50 // 1000) + 1)
            for b in range(b0, b1):
                duck_env[b] = _AMBIENT_DUCK_FACTOR
        # Smooth duck envelope (100 ms attack/release).
        smooth_duck = list(duck_env)
        for b in range(1, n_blocks):
            smooth_duck[b] = 0.72 * smooth_duck[b - 1] + 0.28 * duck_env[b]
        for b in range(n_blocks - 2, -1, -1):
            smooth_duck[b] = 0.72 * smooth_duck[b + 1] + 0.28 * smooth_duck[b]

        fade_in_n = min(total_samples, round(0.8 * sample_rate))
        fade_out_n = min(total_samples, round(1.2 * sample_rate))
        pulse_hz = 2.0 if music_mood == "energetic" else 0.35
        phases = [0.0, 0.0, 0.0, 0.0]
        shimmer_phase = 0.0
        inv_sr = 1.0 / sample_rate
        # Gentle 2-pole ~900 Hz low-pass filter for warm documentary Rhodes texture.
        pad_alpha = min(0.95, (_TWO_PI * 900.0) / (_TWO_PI * 900.0 + sample_rate))
        pad_lp1 = 0.0
        pad_lp2 = 0.0
        for i in range(total_samples):
            chord = chords[(i // bar_n) % len(chords)]
            bar_pos = (i % bar_n) / float(bar_n)
            chord_env = math.sin(math.pi * bar_pos) ** 0.35
            sample = 0.0
            for k, freq in enumerate(chord):
                phases[k] += _TWO_PI * freq * inv_sr
                w = 0.40 if k == 0 else (0.24 if k == 1 else 0.16)
                # Fundamental + soft 2nd-harmonic Rhodes warmth.
                sample += w * (math.sin(phases[k]) + 0.16 * math.sin(2.0 * phases[k]))
            # Subtle detuned top shimmer (+0.6 Hz chorus warmth).
            shimmer_phase += _TWO_PI * (chord[-1] + 0.6) * inv_sr
            sample += 0.06 * math.sin(shimmer_phase)
            pad_lp1 += pad_alpha * (sample - pad_lp1)
            pad_lp2 += pad_alpha * (pad_lp1 - pad_lp2)
            t_s = i * inv_sr
            lfo = 0.86 + 0.14 * math.sin(_TWO_PI * pulse_hz * t_s)
            edge_gain = 1.0
            if i < fade_in_n:
                edge_gain *= i / max(1, fade_in_n)
            rem = total_samples - 1 - i
            if rem < fade_out_n:
                edge_gain *= rem / max(1, fade_out_n)
            duck = smooth_duck[min(n_blocks - 1, i // duck_step)]
            buf[i] += _AMBIENT_BASE_GAIN * edge_gain * chord_env * lfo * duck * pad_lp2

    # 1. Opening hook velvet sub-thump (0..300 ms): smooth 92 Hz -> 44 Hz pitch glide
    if include_hook_thump:
        thump_n = min(total_samples, round(0.300 * sample_rate))
        attack_n = max(1, round(0.010 * sample_rate))
        phase = 0.0
        for i in range(thump_n):
            p = i / max(1, thump_n - 1)
            freq = 44.0 + 48.0 * math.exp(-5.0 * p)
            phase += _TWO_PI * freq / sample_rate
            env = (i / attack_n) if i < attack_n else math.exp(-4.2 * (i - attack_n) / thump_n)
            buf[i] += _HOOK_THUMP_GAIN * env * math.sin(phase)

    # 2. Tasteful airy whooshes centered on spaced A/B jump-cuts (180 ms Hann low-pass breeze)
    chosen = select_sfx_transitions_ms(transition_ms, duration_ms)
    whoosh_n = round(0.180 * sample_rate)
    half_w = whoosh_n // 2
    state = 0x5EED_C1A5
    for cut_ms in chosen:
        center = round(cut_ms * sample_rate / 1000.0)
        start = center - half_w
        lp1 = 0.0
        lp2 = 0.0
        for j in range(whoosh_n):
            idx = start + j
            if idx < 0 or idx >= total_samples:
                continue
            # Deterministic LCG white noise -> 2-pole sweeping low-pass filter (180->720->220 Hz)
            state = (1664525 * state + 1013904223) & 0xFFFFFFFF
            noise = (state / 2147483648.0) - 1.0
            p = j / max(1, whoosh_n - 1)
            hann = math.sin(math.pi * p)
            env = hann * hann
            cutoff = 180.0 + 540.0 * env
            alpha = min(0.95, (_TWO_PI * cutoff) / (_TWO_PI * cutoff + sample_rate))
            lp1 += alpha * (noise - lp1)
            lp2 += alpha * (lp1 - lp2)
            buf[idx] += (_WHOOSH_GAIN * 2.2) * env * lp2

    # 3. Crisp tactile pops for animated stat cards & visual interrupts (55 ms warm pitch drop)
    pop_n = round(0.055 * sample_rate)
    pop_att = max(1, round(0.004 * sample_rate))
    for pop_t_ms in select_sfx_transitions_ms(
        pop_ms, duration_ms, min_spacing_ms=2_500, max_count=8
    ):
        start = round(pop_t_ms * sample_rate / 1000.0)
        phase = 0.0
        for j in range(pop_n):
            idx = start + j
            if idx < 0 or idx >= total_samples:
                continue
            p = j / max(1, pop_n - 1)
            freq = 240.0 + 300.0 * math.exp(-7.5 * p)
            phase += _TWO_PI * freq / sample_rate
            env = (j / pop_att) if j < pop_att else math.exp(-6.5 * (j - pop_att) / pop_n)
            buf[idx] += 0.065 * env * math.sin(phase)

    # 4. Silky 350 ms upward filtered cold-open transition risers leading into beat-0 -> body cuts
    riser_n = round(0.350 * sample_rate)
    r_state = 0xC01D_09E4
    for r_t_ms in select_sfx_transitions_ms(
        riser_ms, duration_ms, min_spacing_ms=3_000, max_count=3
    ):
        end_idx = round(r_t_ms * sample_rate / 1000.0)
        start_idx = end_idx - riser_n
        r_lp1 = 0.0
        r_lp2 = 0.0
        r_phase = 0.0
        for j in range(riser_n):
            idx = start_idx + j
            if idx < 0 or idx >= total_samples:
                continue
            p = j / max(1, riser_n - 1)
            # Exponential upward swell peaking right before the cut, then crisp 15 ms taper.
            taper = 1.0 if p < 0.94 else max(0.0, (1.0 - p) / 0.06)
            env = (p * p) * taper
            r_state = (1664525 * r_state + 1013904223) & 0xFFFFFFFF
            noise = (r_state / 2147483648.0) - 1.0
            cutoff = 220.0 + 1630.0 * (p * p)
            alpha = min(0.95, (_TWO_PI * cutoff) / (_TWO_PI * cutoff + sample_rate))
            r_lp1 += alpha * (noise - r_lp1)
            r_lp2 += alpha * (r_lp1 - r_lp2)
            r_phase += _TWO_PI * (140.0 + 280.0 * p) / sample_rate
            buf[idx] += env * (0.095 * r_lp2 + 0.025 * math.sin(r_phase))

    pcm = array.array("h")
    for s in buf:
        clamped = -1.0 if s < -1.0 else (1.0 if s > 1.0 else s)
        pcm.append(int(round(clamped * 32767.0)))

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return path
