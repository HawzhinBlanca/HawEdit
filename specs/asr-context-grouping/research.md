# ASR Context Grouping Research

Date: 2026-10-06 (Baghdad); baseline 899ab32c0efcdf306245a2dcbe55d8124e436c0e.
Scope: BLUEPRINT Section 3 Stage 1 and Section 4.2. D-181, D-281, D-282 remain
binding. No model, tokenizer, stopping threshold, correction policy or published
quality claim changes. The primary checkout stays frozen during its development
comparison; this isolated worktree is the only source writer.

## Observed Root Behavior

The ZAR38 region 905634..917022 ms reproduces numerical repetition without natural
EOS. All 560 loaded LoRA tensors match the frozen champion bundle after runtime
dtype conversion; 280 adapter layers are active, none disabled, and no model
module is in training mode. Tokenizer and model vocabulary identities agree.
The 7b and 7b_v2 architecture configurations agree after the existing vocabulary
override. These observations reject the proposed inactive-adapter/training-mode
explanations; they do not establish native transcription accuracy.

Greedy and four-beam normalized decoding both fail on the original target. Four
beams plus two-second context completes, but changing beams alone is insufficient.
Adding only the complete previous speech region also fails. All four tested
windows including the complete next region complete naturally with the unchanged
greedy decoder, as does the positive control. This supports a boundary/context
interaction, not a claim that every number or word is faithful.

## Proposed Input Policy

Coalesce whole, ordered VAD intervals when the gap is at most 1000 ms and their
union spans at most 38000 ms. Never split, reorder, duplicate or omit an original
interval. Keep an existing individual interval up to the current 40000-ms interface
ceiling. Refuse malformed, overlapping or unordered input. Stage 0 remains intact;
the policy affects Stage 1 input windows, not source evidence or CTC alignment.

The frozen 547-interval request forms 76 windows under this rule. That is an input
count, not a speed or accuracy result. The 25-row development comparison uses
real OmniAsrBackend.transcribe_segment, natural-completion admission, CTC emissions
and Viterbi alignment, comparing original/grouped inputs. Every target's PCM was
verified identical to its frozen original before trials. Collection closed with
the regressions recorded below; no all-sample pass, raw transcript, benchmark, publication or 10/10 is
claimed. Repeated windows are correlated observations from ONE episode.

## Evidence

Private immutable evidence root:
`C:/Users/Wareen/AppData/Local/HawEditEvidence/asr-isolated-decoder-runtime-20261005/`.
`probe-state` is a retained failed launcher attempt (Windows/WSL virtualized path).
`probe-state-v2` contains eight complete decoder-only trials; `probe-boundaries`
contains eleven complete boundary trials. `probe-groups` contains the completed
50-invocation collection, not a passed producer or acceptance result. `group-stack-01` identifies the decoder, not
CTC, as active during a slow grouped trial. Timing is shared-host, instrumented
development evidence, not an isolated performance claim.

Hardware: HawaPC01, WSL2 Linux 6.18.40.1, two RTX 3090 Ti; Python 3.12.0,
torch 2.8.0/CUDA 12.8, omnilingual-asr 0.2.0, fairseq2 0.6, PEFT 0.19.1,
transformers 4.57.6. Champion identity:
`lora:dfa6237a3b287b7ca6ef88d848a3540ffbf052f8900bd88e99b5e3495d65809d`.

Installed upstream source governs the experiment. Primary documentation inspected:
https://github.com/facebookresearch/omnilingual-asr/blob/main/src/omnilingual_asr/models/wav2vec2_llama/beamsearch.py
and https://github.com/facebookresearch/omnilingual-asr/blob/main/src/omnilingual_asr/models/wav2vec2_llama/config.py.
Read-only stack tooling is an isolated MIT py-spy 0.4.1 CLI, not a runtime dependency:
https://github.com/benfred/py-spy. No model or media was sent to it remotely.

## Remaining Boundaries

Native fidelity, speaker identity, full producer validation, render/export quality,
release CI, current qualified VEX review, reserved-hardware performance, independent
holdouts and sustained acceptance remain separate obligations. Source/voice rights
are already closed; do not reopen them. No paid route is used by this repair.

## Test-First Implementation Checkpoint

The new contract file produced 24 expected failures before implementation. The
first affected-file run retained one erroneous test fixture: 59001 minus 21001
is exactly 38000, so merging was correct. Changing that input endpoint to 59002
tests the intended over-budget refusal; no implementation limit or assertion was
weakened. The next run passed 229 cases. A separate type diagnostic found a
non-exported subprocess module access in the new test, now corrected by patching
the actual imported subprocess module. The latest affected-file run (green-v3)
passes 229 tests, zero failures/errors/skips, JUnit 43.177 seconds. Source hashes
are unchanged through each run; real PCM cutting is exercised, while controlled
backend/worker output remains explicitly component evidence, not native accuracy.

Private records: asr-context-unit-20261006/{red,green,green-v2,green-v3}/ under
the HawEditEvidence root. Worktree ASR SHA256 at green-v3:
cbc74c744c6dfc2daf3f6dd89b1f3fbea4fb754ff136dcbf611d0c83c9971c87;
test file: 9cec76fdc7506011b586d1bf7a904230d6abd6b91e5908f0a2236e54b6067d2d.
These uncommitted diagnostics are not the exact gate, CI or completion evidence.

## Adverse Interim Finding And Next Development Protocol

Invocation 30 of the still-active 50-invocation comparison refuses dev-15 under
grouped input with DecodeIncomplete. Its original 1803298..1804734-ms input
completed; the group 1792802..1827326 ms (34524 ms, under the 38000-ms budget)
does not demonstrate natural EOS. Group PCM SHA256:
07e15def9ad7c6239b4f895893ebe0bf67fdd8ab300409ed071c99eb816fe4fc.
This is a candidate regression, not an acceptable publication refusal rate or a
reason to activate the 38000-ms default. Finish the fixed comparison and retain
all arms. The staged isolated implementation is not integrated into primary.

Before further trials, predeclare a separate 18000-ms/1000-ms input-budget study
using ALL 25 selected development/risk rows. Read-only mapping forms 158 windows;
risk-01 includes 905634..920094 ms (the complete next-region union already tested)
and dev-15 uses 1796034..1804734 ms. This is development iteration, not a new
holdout or a lowered acceptance threshold. No alternate decoder, weights, output
trimming, forced EOS or first-failure production continuation is authorized.

Run the next study only after the previous full comparison's terminal and all
owned processes are closed. Use the same receipt/source/runtime; validate loaded
adapter tensors and target PCM again. All 25 grouped invocations are risk-first;
the complete previous original arm is retained by hash, including every failure.
Observe actual generator call/return terminal tokens with line tracing disabled,
while real transcribe_segment still enforces pinned completion admission and CTC
alignment. Do not fabricate per-step guard observations or compare these timings
with the slower traced run. Native accuracy, full validation and publication remain
unmeasured. Do not integrate any budget merely because it helps the known excerpt.

Prepared external worker SHA256:
b97332da110d800b4e0cbd74a12ec0274aef6f8bd76cd62a948841db29515184;
controller: 46a33dfb79707b2a5a722416816b9afae36806443eac2fe3d1b8501ccefe0775.
Files: C:/Users/Wareen/{probe_hawedit_context18_899.py,run_hawedit_context18_899.py}.
They parsed before execution; the narrower study subsequently started only after
the full baseline terminal and verified owned process closure. Its active immutable
record root is probe-groups-span18000 under the same private evidence base.

## Closed Wider Comparison

All 50 prescribed invocations collected at unchanged primary source 899ab32,
unchanged watched inputs and restored decoder configuration. Controller elapsed
5217.071957 seconds, including load and instrumented development work; not an
isolated performance result. Original input: 22 aligned, three refusals (risk-01
and risk-02 DecodeIncomplete; risk-03 AlignmentInfeasible, 18 frames/226 tokens).
Grouped input: 23 aligned, two refusals (dev-15 and dev-18 DecodeIncomplete).
All five risk grouped arms aligned, but the two new control regressions REJECT
the 38000-ms candidate. Counts are correlated development observations from one
episode, not independent jobs, fidelity ratings or editorial-quality percentages.
No raw transcript, review MP4 or publication was produced by this experiment.

Sealed stdout SHA256:
b6bd75abf3c217ed87c431556410783f7b022df4efba44e3f1881710c023d6c1.
Terminal JSON SHA256:
25fb5a4787b928785f05278416791261988b48634434ae37604d1b72259f7007.
The narrower study is still collecting; no passing default is selected yet.
