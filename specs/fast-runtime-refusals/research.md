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
