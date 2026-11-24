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
from typing import Final

__all__ = [
    "DEFAULT_SFX_SAMPLE_RATE",
    "select_sfx_transitions_ms",
    "write_cinema_sfx_wav",
]

DEFAULT_SFX_SAMPLE_RATE: Final[int] = 48_000
_HOOK_THUMP_GAIN: Final[float] = 0.070  # ~ -23 dBFS
_WHOOSH_GAIN: Final[float] = 0.050  # ~ -26 dBFS
_TWO_PI: Final[float] = 2.0 * math.pi


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
    sample_rate: int = DEFAULT_SFX_SAMPLE_RATE,
    include_hook_thump: bool = True,
) -> Path:
    """Write a deterministic 16-bit mono PCM WAV bed of subtle cinema micro-SFX."""
    if duration_ms <= 0:
        raise ValueError(f"duration_ms must be positive, got {duration_ms}")
    if sample_rate <= 0:
        raise ValueError(f"sample_rate must be positive, got {sample_rate}")

    total_samples = max(1, round(duration_ms * sample_rate / 1000.0))
    buf = array.array("f", [0.0]) * total_samples

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
