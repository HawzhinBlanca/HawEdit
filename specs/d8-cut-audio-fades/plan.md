# Plan — ~30 ms audio fades at cuts (D8 / d8-cut-audio-fades)

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"

Read `research.md` and `spec.md` first. Probe script: `captures/probe_d8.py.txt`.

## Approach

Extract one shared fade helper (no duplicated filter-building code across `silence.py`, `assembly.py`, and `render.py`) applying `CUT_AUDIO_FADE_MS = 30` (`curve=qsin`) at every cut edge:

1. **Shared helper (`audio_cut_fade_filters` in `src/hawedit/silence.py`)**:
   - Given `duration_ms: int`, `fade_in: bool`, `fade_out: bool`, `fade_ms: int = CUT_AUDIO_FADE_MS`:
     computes `fade_s = min(fade_ms / 1000.0, (duration_ms / 1000.0) / 2.0)` (empty if `duration_ms <= 0`) and returns the `afade=t=in:st=0:d=...:curve=qsin` / `afade=t=out:st=...:d=...:curve=qsin` filter terms.
2. **Apply at all three multi-cut splice builders**:
   - `silence_trim_filter` (`src/hawedit/silence.py:521`): fade-out at end of each segment `i < n - 1`, fade-in at start of each segment `i > 0` (plus outer edges optional/via `render_clip`).
   - `assembled_splice_filter` (`src/hawedit/assembly.py:253`): identical boundary fades at every splice cut between `AssemblySpan`s.
   - `measure_audio_loudness` (`src/hawedit/render.py:347`): use the same boundary fades when `len(retained_intervals_ms) > 1` so Pass 1 matches Pass 2.
3. **Apply outer clip-edge `30 ms` fade-in/out in `render_clip` (`src/hawedit/render.py:1676-1843`)** (prepended on the audio chain before `loudnorm`, keeping `audio_filter()` pure and preserving its unit tests) and in `render_assembled_reel` (`src/hawedit/assembly.py:330`).

## Files and symbols

| File | Symbol | Change |
|---|---|---|
| `src/hawedit/silence.py` | `CUT_AUDIO_FADE_MS`, `audio_cut_fade_filters`, `silence_trim_filter` (`:521`) | Add shared `30 ms` `qsin` fade helper; emit cut fades in `silence_trim_filter` |
| `src/hawedit/assembly.py` | `assembled_splice_filter` (`:253`), `render_assembled_reel` (`:330`) | Reuse `audio_cut_fade_filters` on splice boundaries and outer edges |
| `src/hawedit/render.py` | `measure_audio_loudness` (`:347`), `render_clip` (`:1676-1843`) | Reuse `audio_cut_fade_filters` on `retained_intervals_ms` splice and clip outer cut edges |
| `tests/test_silence.py`, `tests/test_assembly.py`, `tests/test_render.py` | `:299`, `:207`, new AC1–AC3 tests | Update raw-filter string assertions to verify `afade`; add PCM discontinuity & A/V-sync tests |
| `DECISIONS.md` | `## D-351` | Document `30 ms` `qsin` boundary `afade` policy across all cut/splice paths |

## Divergence and ADR

Implements `BLUEPRINT.md` §3 Stage 6; no divergence from `BLUEPRINT.md`. Documented in **D-351**.

## Risks and owner actions

1. **Test updates**: `tests/test_silence.py:307` and `tests/test_assembly.py:215` currently assert the unfaded `[a0]` filter string; updating them to check `afade` clauses is part of T1.
2. **VEX binding**: Editing `src/hawedit/**` moves `package_digest(src/hawedit)` (`security/wsl-asr-vex.json`).
