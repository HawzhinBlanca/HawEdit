# Fast Runtime Refusal Research

Approval basis: Wareen's approved full repair plan, repeated "fix all" direction
and current "continue" instruction. No new authority, dependency, model,
installation, spending, publication or acceptance-threshold change.

Exact full gate at e243f66da8c7008f17d5b0de7bffd984b90862a5 on HawaPC01,
Windows26300/Python3.12.10:6184 passed/7 failed/3 errors. Two real NVENC probes
raised subprocess.TimeoutExpired at30s;0-byte ingest took5.312s against the
existing2s bound. Preserve the full log and gate report. These failures justify
small refusal fixes, not weakening the real encode or elapsed-time assertions.

Actual installed Serena four-pair map at f239cae (unchanged production source),
C:/Users/Wareen/HawEditFastRefusalMap-20261012/serena-map.json, SHA256
351c0c901e1444414b5a3bf3964fa54bb12d0d9a17a0714d3259587f1615fd3a.
Definitions and references were read before source changes.

encoder_available currently attempts a real Stage6-sized encode, but leaves
process launch and timeout exceptions unhandled. Ingest currently discovers
ffmpeg and creates work before rejecting an empty source through extraction.
An empty file is independently invalid and can be refused before launching any
media decoder. Existing source hashing and valid-media probing must remain.
BLUEPRINT Stage0/§4.3.2/§6; existing no-silent-encoder-substitution contract.

The inherited audit-stream deadline failure is separate and not fixed by these
changes. VEX source binding/expiry likewise needs qualified review, not rebinding.

## Red/Green Caller Evidence

Both new regressions failed before the change: empty ingest created work before
refusing, and unavailable executable probing raised FileNotFoundError. After
the scoped changes, tests/test_fast_runtime_refusals.py plus tests/test_soak.py
passed. The complete ingest/soak/render/new-refusal cohort then exited0 with
all dot outcomes, preserving the real encode comparison, explicit no-fallback
refusal and repeat-render checks. Log:
C:/Users/Wareen/HawEditFastRefusalCohort-20261012.log. No core operation was mocked
in the new regressions. Full same-commit gate/CI remains required; this is not
a completed-task, video-quality or current VEX claim.

## Committed Follow-Up Evidence

Exact b78dacf92442c81d862e8b6a8245ad1068b91cbf full gate:6194 passed/3 failed,
1 warning in4731.32s on HawaPC01/Windows26300/Python3.12.10. Source/status
were unchanged. Original generated XML is copied unchanged outside .gate,
HawEditGateEvidence-b78dacf-20261012, SHA256
f8613e1485d04042b0d9bffcad919841f8ae102d91f9830764ffae7b37d74b71.
No harness, fixture or threshold change. The inherited audit deadline and wheel
build outcomes now pass; VEX still requires a qualified current-source review.

The real NVENC comparison takes158.143s and shows independent encode success
while the helper returnsFalse. The helper's lru_cache stores failure/timeout
forever, despite runtime availability being mutable. Prove this deterministically
with a missing executable that later becomes a real copied ffmpeg at the same
path, without mocking the subprocess or encoder. Probe on each request instead
of caching either positive or negative availability. Retain30s launch/encode
bound, actual Stage6-sized output and explicit no-substitution behavior.

The actual truncated MP4 test takes2.563s against its unchanged2s bound.
Its physical first ftyp atom declares32bytes in a12byte file. Read only16bytes
and parse the standard big-endian size/type fields with struct before decoder
discovery. Refuse only a recognized ftyp whose ordinary/extended/EOF-sized atom
cannot be complete; unknown containers and complete headers still go through
the existing real decoding/hash checks. This is not a general media parser or
an admission claim. Physical truncated/extended headers must refuse even when
ffmpeg is absent, without work creation.

Actual installed Serena current definition/reference pairs before these edits:
HawEditFastRefusalsFollowupMap-b78dacf-20261012/serena-map.json,
SHA25624924c002645421340c8fc769501c577182b7a71353d70bc08096ec38d6b2686,
unchangedTrue. Same pipeline/render/test callers as impact-map.md; no public
signature, dependency, security-policy or model change.

## Follow-Up Result And Remaining Encoder Refusal

All five focused physical regressions pass; three new instances failed first.
Fast lint/mypy393 pass. The complete173-instance ingest/soak/render/refusal
cohort still has one failure: the existing real NVENC comparison. All other
outcomes, including truncated-input timing and repeat renders, pass. Log:
HawEditFastRefusalFollowupCohort-20261012.log. Cache removal fixes the independently
demonstrated stale executable result, but is NOT sufficient to resolve this
host's NVENC startup problem. No whole-cohort success is claimed.

Fresh separate physical encode/decode calibration on HawaPC01/Windows26300,
Python3.12.10, FFmpeg8.1.1-full SHA09948d4cdd0650da6ff5a87577469f2a218dc2615ae379f8f734d24c49de0f73,
host NVIDIA driver610.88, confirms x264 returns0 in0.157s and independently
decodes6220800 RGB bytes (1080x1920), decode0.093s. NVENC exceeds the configured
30s subprocess communication timeout, returns no complete output and decodes
zero frames. Observed total is40.407s: process creation/cleanup is outside that
subprocess timeout. The30s argument is NOT a proved end-to-end wall-clock bound.
HawEditEncoderResult-20261012/observation.json records source/package/status,
binary hash and all raw exit/refusal/decode results. This is not a reel or
benchmark acceptance result. Do not call timeout evidence a missing driver.

Separate original topology calibration with explicit GPU0/GPU1 and single
encoder/filter threads also times out without bytes or decoded frames:
48.703s /47.594s total respectively. HawEditEncoderTopology-20261012 contains
unchanged-source evidence and exact commands. It does not justify choosing a
GPU, increasing the product timeout, changing drivers, weakening the existing
comparison or silently substituting x264. Keep the remaining refusal visible
and require further lifecycle/driver diagnosis. An explicitly selected x264
route is distinct from a hidden NVENC fallback. No task promotion or VEX renewal.
