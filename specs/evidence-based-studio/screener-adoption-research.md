# Screener Adoption Research

2026-10-03. Baseline clean local4e3ec77f834e875c0a3e6e4867dc44d8d2044380,
producer3de6c080ab1d7824cfdca44e61e03304f8d03db1903a6d403e3bfdd3699669e3.
Previous goal turn: progress (committed ASR identity repair, actual full gate4446 passes/
one VEX failure, zero skips). Read current vault checkpoint and source before this research.

## Source Findings

Shared build_and_run accepts judge_transport, which covers discovery/judgment. Optional
GeminiFlashScreener and JevScreener instead use independent urllib transports. get_screener
cannot receive a guarded transport, and the shared builder forwards the screener name for
late construction inside run_pipeline. Thus a protected worker cannot adopt every egress
through the shared construction boundary without bypassing its own authority/pool controls.
Transport injection alone is not authentication; do not certify a callback as owner approval.

Gemini parsing defaults absent score fields to zero, coerces string booleans/numbers, accepts
duplicate/foreign/omitted candidate IDs and ignores response structure. Jev's legacy codec
also invents absent answers/probabilities and clamps out-of-range values. Dataclass range
checks admit Boolean scores and do not validate self-containment identity/types. Both default
HTTP transports read unbounded bodies. These are actual source defects, not quality evidence.

## TypeSafe Contract Contradiction

Official current API requires model and typed question criteria, and returns answers, not
the questions/answer/probability shape in our synthetic legacy test. Score requires2-10
descriptive levels and returns a weighted level position/distribution/legend/confidence;
Noul returns P(true), not a Boolean. Our current request omits model/criteria and asks an
unsupported scalar min/max range. An old synthetic success cannot establish live compatibility.
[Official API](https://docs.typesafe.ai/api),
[Score](https://docs.typesafe.ai/primitives/score),
[Noul](https://docs.typesafe.ai/primitives/noul), retrieved2026-10-03.

Do not silently choose a new optional model/rubric/threshold while fixing transport and
measurement integrity. A separately recorded current-wire/model-policy unit, development
evidence and owner resource/governance review remain required before calling Jev supported
in production. This unit removes invented legacy measurements and refuses mismatched actual
typed responses contextually; it does not claim to repair/evaluate the current Jev API.
No new provider/model access, spending or licence acceptance occurs.

## Approved Repair Boundary

Necessary T3/T5 shared-producer/guarded-egress and truthful-score repair within the already
approved parent plan, D-275/D-276 and BLUEPRINT sections2-5. Preserve canonical ASR/judge,
existing screener selection/defaults, composite coefficients, valid legacy diagnostics,
ordinary CLI/durable behavior and every original assertion. No new dependency/fixture edit.

Add optional keyword-only screener_transport to the shared builder/factory. When a guarded
judge transport is supplied and screening is selected, require a separate explicit transport
before source/model/credential work; no fallback to direct HTTP. The supervisor must still
authenticate actual screener authority, confidentiality, pricing and shared allocation.
Construct selected screeners through the real factory with the injected request transport.
Never infer that the existing canonical Pro policy authorizes Flash or TypeSafe.

Require actual bounded finite numeric/Boolean fields, strict JSON duplicate/nonfinite refusal,
valid unique input IDs and complete matching Gemini batch identity before ranking. Unknown
measurements cannot become zeros or confidence. Reject oversized responses; preserve valid
ranking and explicit no-screener behavior. Keep original raw provider dictionaries on results
without turning predictions into publication/semantic-fidelity authority.

Actual pre-edit Serena maps/logs are captured in LocalAppData/HawEditEvidence. Complete the
definition/reference records and caller impact before implementation. Test first, then run
the exact gate on a reviewed frozen clean local commit. No task/ledger promotion until current
gate and required same-SHA CI. Protected worker, attempt/recovery, HTTP identity, revisions,
signed review/export and every independent/sustained acceptance threshold remain mandatory.
