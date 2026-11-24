# Research — ~30 ms audio fades at cuts (D8 / d8-cut-audio-fades)

**Provenance.** 2026-11-18, branch `gemini/lane-4` at commit `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf`. Host `HawaPC01`, Windows 11 (`Windows-11-10.0.26300-SP0`), `.venv` CPython `3.12.10`, NumPy, `ffmpeg 8.1.1-full_build-www.gyan.dev`. Test inputs: `tests/fixtures/kurdish-speech-3cuts.mp4` (`sha256:ed038e743a6b1ee167290741ceda926ac1077ff192e4910528017e3183655a15`) and `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4` (`sha256:6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0`). Serena MCP was unavailable in this session; callers mapped with `rg`. Probe script: `specs/d8-cut-audio-fades/captures/probe_d8.py.txt`.

## Defect (measured PCM discontinuity at cuts)

Every audio cut path currently trims and concatenates raw waveforms with zero boundary fade:
1. `silence_trim_filter` (`src/hawedit/silence.py:521-543`): emits `[0:a]atrim=...,asetpts=PTS-STARTPTS[a{i}]` then `concat=n=k:v=1:a=1`.
2. `assembled_splice_filter` (`src/hawedit/assembly.py:253-275`): emits identical raw `atrim` + `asetpts` + `concat`.
3. `measure_audio_loudness` (`src/hawedit/render.py:347-363`): Pass 1 `loudnorm` measurement with `retained_intervals_ms` builds the same raw `atrim` + `concat`.
4. `render_clip` (`src/hawedit/render.py:1676-1843`): cuts clip start (`-ss`) and clip end (`-t`) directly from the source audio without edge fades.

Why `afade` on each trimmed segment boundary rather than `acrossfade`:
- `acrossfade=d=0.030` **overlaps** segments and shortens the audio stream by `30 ms` per cut, breaking A/V sync (`concat` video does not shorten), failing `assert_encoded_span(measured_ms, effective_duration_ms)` (`render.py:1918`), and shifting speech behind captions.
- Per-segment `afade=t=out` (trailing `30 ms` before each cut) + `afade=t=in` (leading `30 ms` after each cut) with `curve=qsin` preserves **exact** duration (`0 ms` A/V drift) while driving waveform amplitude smoothly through zero at every cut.

Measured PCM discontinuities (`48 kHz` mono `f32le` via `ffmpeg`):

| Source & splice | Condition | Output duration | `tight_max_step` (`±5 ms` at cut) | `boundary_1ms_peak` (`±1 ms` at cut) |
|---|---|---|---|---|
| `kurdish-speech-3cuts.mp4` (`2.0–3.2 s` + `0.2–1.2 s`, cut `1.200 s`) | Current raw `atrim` | `2200.0 ms` (mp4 `2200 ms`) | `0.03880` | `0.06064` |
| `kurdish-speech-3cuts.mp4` (same splice) | `30 ms` `qsin` `afade` | `2200.0 ms` (mp4 `2200 ms`) | **`0.00934`** (`4.15×` lower) | **`0.00165`** (`36.8×` lower) |
| `zar-ai-lamo` excerpt (`5.0–8.5 s` + `18.0–21.5 s`, cut `3.500 s`) | Current raw `atrim` | `7020.0 ms` | `0.04150` | `0.23853` |
| `zar-ai-lamo` excerpt (same splice) | `30 ms` `qsin` `afade` | `7020.0 ms` | **`0.00259`** (`16.0×` lower) | **`0.00975`** (`24.5×` lower) |

## Symbols and references

- `src/hawedit/silence.py:521` (`silence_trim_filter`); `src/hawedit/assembly.py:253` (`assembled_splice_filter`), `:330` (`render_assembled_reel`); `src/hawedit/render.py:347` (`measure_audio_loudness`), `:1676-1843` (`render_clip`).
- Existing tests pinning raw filter text: `tests/test_silence.py:299-311`, `tests/test_assembly.py:207-219`.
- Blueprint / ADR refs: `BLUEPRINT.md` §3 Stage 6; `DECISIONS.md` D-264 (`:13748`), D-282 (`:13963`).

## Risks

- Two existing unit tests (`tests/test_silence.py:307`, `tests/test_assembly.py:215`) assert exact literal substrings `[0:a]atrim=...,asetpts=PTS-STARTPTS[a0]` without `afade`; those assertions must be updated alongside the implementation.
- Short segments (`duration_ms < 60 ms`): `fade_s` must be clamped to `min(0.030, seg_dur_s / 2.0)` so `afade=t=in` and `afade=t=out` never cross or fail ffmpeg validation.
- VEX binding: Editing `src/hawedit/**` moves `package_digest(src/hawedit)` (`security/wsl-asr-vex.json`).
