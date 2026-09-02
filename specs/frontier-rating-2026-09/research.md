# Research — frontier rating, September 2026

> Question: rate HawEdit honestly against the best repurposing products of September 2026 on
> content awareness, model use, architecture, reliability and "team of editors" flexibility —
> with final editing done in DaVinci Resolve, not in HawEdit — and name the best truly
> achievable state this month. Serena timed out at session start; the code map is
> `specs/pro-grade-program/research.md` (2026-09-02, cites by file:line) plus greps below.
> Measured facts on `HAWAPC01` 2026-09-02: 2× RTX 3090 Ti 24 GB, 3990X, 256 GB RAM.

## Files, symbols, data flow (what a Resolve handoff touches)

- `delivery.py:build_edl` — CMX 3600, **two events** (V, A), source timecode in, record from 0
  (`delivery.py:256-300`). `build_srt`. Nothing else leaves for an editor.
- `clip.py:Output.to_dict` — `crop_target` is a **string** (`clip.py:516`); no crop keyframes,
  no punch-in list, no caption events in the editing JSON. The edit lives only in the ffmpeg
  command (`render.py:465-576`) and the ASS file.
- `pipeline.py:2458` — `punch_in_schedule(...)` is computed at render time and never persisted.
- `reframe.py:stabilize` — the camera path is a keyframe list already (`reframe.py:306-408`);
  it is consumed by `render.crop_filter` and discarded.
- Stage 6 renders `crop → scale → ass → loudnorm → nvenc` in one pass (`render.py:793-839`).
- Editorial inputs that *should* travel to the editor: verdict fields (`gemini.py:205`), SV6D
  text (`video_reader.py:92-107`), Path A `reason_ckb` (**discarded**, `path_a.py:302`),
  sentence table (`sentences.py:119-169`), shot cuts and VAD (`ingest.py:500-542`),
  diarization turns (`--diarize`).

## Current behaviour, by §3 stage

Stage 0 real (shots, VAD, proxy). Stage 1 real but **not runnable this instant**: the WSL
receipt for the current source digest `82d4b258…` is missing (`python -m hawedit.models`:
9/15 available; OmniASR ×2, validator, pyannote, both Gemini ids missing — the uncommitted
tree moved the digest). Stage 2 real. Stage 3: Path A real, text-only, non-reproducible; Path B
seeded by Path A's rank-1 (`pipeline.py:1351-1376`). Stage 4: one billed call per candidate,
≤ 20 JPEGs, no anchors. Stage 5 correct and outward-only. Stage 6: face-tracked (Haar, 2 fps),
punch-ins, karaoke, hook card, single-pass loudnorm. Delivery: five files, atomic.

## Integration points and callers to keep working

`render_clip` (pipeline, `proposals.py` revision path, `render_agent.py`), `build_edl` and
`build_srt` (`delivery.py`, tests), `Output` schema readers (`clip.py`, `judge.py:349`,
agents' `inspect_run`). A richer editing JSON must stay loadable by `Clip.from_dict`
(`clip.py:531` optional-field set) and by `tests/test_claims.py`'s contract assertions.

## Risks (what skips silently, what has no test)

- No test opens the EDL in any NLE; the EDL carries no cut, reframe or caption decision.
- DaVinci Resolve is **not installed** on `HAWAPC01` (only `…/DaVinci Resolve/audio`); no
  scripting API to verify any timeline import against.
- `captions_burned_in`, `FACE_TRACKED`, `human_reviewed` are labels (`pro-grade-program`
  research §5); a Resolve handoff inherits them unless T1.2 lands first.
- Everything editorial is unmeasured on Sorani: no labelled set (`BLOCKED.md` #1, #H2).

## What it answers to

`BLUEPRINT.md` line 6 — *"Output: validated clip candidates with exact boundaries, Kurdish
captions, editing JSON / EDL"* — and §2's delivery line *"MP4 · SRT/ASS · editing JSON · EDL"*
after a *"HUMAN QC GATE (always)"*. The editor handoff **is** the spec's primary output; the
in-house render is Stage 6's convenience. No § names Resolve, FCPXML or OTIO; a timeline
format beyond CMX 3600 is an ADR. `D-041` binds captions to the clip timeline. `BLOCKED.md`
#4 (diarization), #17 (8-frame window), #18 (Path A query), #21 (adapter licence). Model lock
canon: cloud judge is Gemini 2.5 Pro only; Kurdish-specific models first.

## Frontier comparison and the achievable September 2026 state

_(pending the two web-research reports — filled below when they land)_
