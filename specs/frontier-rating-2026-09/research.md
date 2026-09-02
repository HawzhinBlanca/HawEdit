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

## Frontier facts that bound the rating (web research 2026-09-02; vendor vs independent marked)

- **No clipper lists Central Kurdish.** Opus Clip (25 langs), Vizard (37), Descript (Latin
  script only), Submagic (49, Arabic yes), Klap, Captions, Quso, Spikes, 2short, Kapwing, Munch
  (pivoted to done-for-you posts, Aug 2026) — none has ckb. Best external ckb engine:
  ElevenLabs Scribe **32.1 % WER** FLEURS (vendor). OmniASR LLM-7B: **CER 6.0** ckb (Meta CSV).
- **Selection accuracy in the field** (vendor benchmarks, one duplicated corpus): Opus 92 %
  single-speaker / **68 % multi-speaker**, Vizard 78/55, Descript 85/72; Opus discards
  ~40 % (BIGVU, competitor, 2026-07). Nobody exports **EDL or OTIO**; only Opus (XML, Pro) and
  Descript (FCPXML/Premiere XML) hand a timeline to Resolve.
- **Resolve 21** (final 2026-06-03): still **no clip-selection**. Resolve 20 added SmartSwitch
  (speaker-based multicam), IntelliCut (silence removal), Animated Subtitles; Smart Reframe is
  Studio-only, subject-tracking, no audio. Scripting API v21: import AAF/EDL/XML/FCPXML/OTIO,
  `AppendToTimeline`, `AddMarker`; **no transform-keyframe API**; EDL/OTIO carry no transforms.
- **Models, licence-clean, fit a 3090:** pyannote community-1 (CC-BY-4.0, gated) is the best
  open diarizer; Light-ASD / LR-ASD (MIT, ≤1 M params, 94.1–94.45 AVA mAP) for active speaker;
  YuNet (MIT) over Haar; TimeLens2-4B (2026-07) SOTA open grounding; VideoChat3-4B 2026-07;
  Gemini 2.5 Pro stable, no shutdown date; 3.1 Pro preview at 1.6× the price. Video input at low
  resolution ≈ **$0.01/min** on 2.5 Pro. SCRFD/insightface, DiariZen, MMS aligner: **NC, reject**.
- **Engagement prediction has one measured validity number:** SROCC **0.71** (SnapUGC, 120 k
  videos). Every "virality score" is marketing on top of that ceiling.
- **Browser Use `video-use`** (MIT): Scribe → LLM edits text → ffmpeg; a rough-cut agent, no
  selection, no reframing, no NLE export. **Palmier Pro**: a macOS NLE with an MCP server and
  XML export; not a clipper. Neither competes on the selection problem.

## The achievable state this month (what the plan should target)

HawEdit as the **Sorani editorial brain plus proof**; Resolve as the finishing room. Ship per
episode: N sentence-complete clips, an OTIO timeline with cuts and markers (hook, payoff,
punch-in, speaker turns), SRT + ASS, editing JSON carrying the reframe keyframes, a preview
render, and the measured-and-reconciled sidecar. Drop from HawEdit what Resolve does better
(final colour, mix, brand kit, push-ins, encode polish). Keep and finish what nobody else has:
OmniASR + champion, sentence-hard boundaries, judge with frames, diarization + Light-ASD
speaker markers, RTL captions, the reconciliation gate. Needs: #4 click, Resolve Studio
purchase, labels (H2/H13). Plan follows in `plan.md`; `pro-grade-program/tasks.md` shrinks.
