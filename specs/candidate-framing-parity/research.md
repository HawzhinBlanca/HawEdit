# Candidate framing parity: quality investigation

Date: 2026-10-04. Baseline: `7fa7d3a37efb8f11d68ecc2b9a52ecd082f7535e`.
Scope: research and decoded-media diagnostics, not an implemented repair or quality score.

## What the user is asking for

Better finished Sorani reels, not merely safer failure handling. The ASR halt unit
does not establish better selection, storytelling, captions, pacing or framing.
The current ZAR38 test produced no candidates or reels; its three unaligned spans
and two rejected corrections remain unresolved. Do not call an old episode-29 reel
a new ZAR38 result. Exact user-criticized output identification is pending.

## Fresh observations

Read-only media inspection saved native-resolution decoded PNGs from ZAR38 and three
older outputs. All four input video hashes stayed unchanged. Records and commands:
`C:/Users/Wareen/HawEditQuality-7fa7-20261004/media-inspection.json`.
Tools: native CPython 3.12.10; FFmpeg/FFprobe 8.1.1 Gyan full build. No inference,
paid calls, human review or publication was performed.

- The episode-29 review samples at 2s and 12s show different useful subject views.
  These stills cannot establish correct speaker identity, motion stability or sync.
- The older file named `ep29-pro-10-out-of-10-masterpiece.mp4`, sampled at 22s,
  puts red headline graphics over the subject's forehead. This is an observed
  composition conflict, not a native-language fidelity or continuous-video verdict.
- ZAR38's sampled 60s picture is 640x360 and contains an existing source lower-third.
  Its 1080x1920 output canvas would not establish original 1080p picture detail.
  Crop, extra zoom and new text need source-aware review; source graphics cannot be
  assumed absent. Neither upscaling nor extra effects supplies missing detail.

Other saved frames were decoded but not all manually inspected. There is no
uninterrupted audiovisual or native-editor review of these files in this investigation.

## Confirmed execution defect

Actual Serena `find_symbol` and `find_referencing_symbols` mapped seven symbols.
Full definitions, referencing locations, hashes, timestamps and clean source status:
`C:/Users/Wareen/HawEditQuality-7fa7-20261004/framing-impact-map.json`.

`pipeline._render_episode_single_clip` accepts `speaker_tracker`, `two_person_split`
and `min_face_share`, but its tracking block only calls `subject_tracker`. It never
calls speaker association, initializes `split_crops` to None, and serializes the
visual effective configuration with literal `two_person_split="auto"` and empty
speaker turns. The single-clip path does have speaker-association admission checks.

Correction from implementation preflight: `min_face_share` is forwarded to delivery
reconciliation in the episode path. Its presence in the signature is not an ignored
measurement option. The confirmed bypass is speaker association and split execution/
recording; do not widen it into a claim that every input option is ignored.

A genuine pipeline diagnostic reproduced this difference twice, once with default
profile and once with `profile="production"`. Existing decoded 4.2-second fixture,
synthetic test transcript/discovery/judge, no diarizer, requested speaker tracker,
requested split mode `always`, no QC or signature:

| Route | Tracker calls | Private MP4 candidates | Observed outcome |
|---|---:|---:|---|
| Single | 0 | 0 | Refuses missing measured diarization |
| Episode | 0 | 2 | Renders static-centre candidates; plans record `auto` |

Records: `framing-parity-probe.json` and `production-framing-parity-probe.json`
under the private quality evidence directory. Each has the fixture hash, request
scope and saved run/plan paths. The synthetic judge's numbers are test inputs,
not editorial measurements or actual Gemini responses. These outputs are diagnostics,
not approved reels. Existing fixture bytes remained unchanged. No protected fixtures,
gate files, model assets, policy or runtime source were manually edited.

The default and production diagnostics establish ignored requested policy; they do
not establish actual wrong-person frequency on a real corpus. Fixing this defect
does not validate the existing motion associator against labelled identities.

## Requirements and limits

Grounding: BLUEPRINT sections 2-5 and 8.1-8.3; D-263 measured delivery, D-269
RTL captions, D-274 episode orchestration, D-276/D-277 private review and exact
approval. Preserve champion-only ASR and the original source/transcript.

BLOCKED #4/#21 still limit real diarization/model rights, #24 prevents a green
current-source gate, and #1/#25 limit independent corpus/editor acceptance.
No date/hash rebinding can replace the qualified VEX review. No task is done:
the last exact gate remains red, with its original failure preserved.

Recommended sequence: diagnose ZAR38 ASR against native reference; repair this
camera-policy bypass; then source-aware text/layout, caption readability, semantic
pacing and source/output comparison, each with a separate caller map and scope.
More effects, a custom hand-cut, or generic affirmative critic flags are not proof
of a research-grade reusable editorial pipeline.
