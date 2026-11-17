# Transcript Start Research

Baseline: fdfe25e8c80a58d95f312cbb0258808638f66552, 2026-10-04 UTC.
Approved parent T2/T5 scope: truthful stage events, BLUEPRINT sections 2--5.

run_pipeline constructs RunEventLog at line 2750 and calls the ASR producer at 2832,
but emits transcript STARTED at 2892, after inference returns. A RuntimeError projection
returns before that start or a transcript SKIPPED event. Real ZAR38 ASR took 7814.9197 s
including preparation/postprocessing; this source defect prevents the event consumer from
knowing that transcript work began during the expensive call. This is static sequencing
plus actual runtime evidence, not an observed current-browser acceptance claim.

Actual Serena definitions/references: transcript-events-before-map.json (five queries)
and transcript-alias-before-map.json (public alias). Both bind the clean baseline SHA and
retain file-symbol fallback warnings. These are real LSP queries through the installed SDK.
The original maps/logs and runtime artifacts are retained in the private owner evidence
directory zar38-recovery-fdfe25-20261004. No private media/transcript is copied into Git.

RunEventLog.started and finished retain their current signatures and event enum. Failure
events belong to the workflow caller; an operational refusal has a SKIPPED stage terminal
carrying its actual StageSkipped reason. Preserve existing completed order (visual_windows
before transcript) by moving only the start before producer/cache work. Do not invent
within-stage percentages, expose an ETA or claim completed ASR when the report refuses it.

The real ZAR38 artifact contains three unaligned regions and two failed corrections. Its
raw bytes remain immutable; a byte-identical failed-checkpoint replay preserved all errors
in 5.5166 s. A real-model reproduction of the first gap emitted a 266-digit final token,
401 acoustic tokens and 268 repeated pairs; 569 frames cannot support the 669-frame minimum.
Unknown-token count was zero. This confirms a repeated-digit hypothesis, not a reason to
weaken alignment or infer the intended number. Accuracy remains unmeasured. This unit
does not repair model quality, change canonical decoding, continue failed production,
authenticate cloud authority or approve publication. It only repairs stage observation.
