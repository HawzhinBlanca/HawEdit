# Screener Adoption Caller Impact

Baseline4e3ec77. Actual pre-edit LSP records: screener-adoption-before-map.json plus
supplementary screener-defaults-before-map.json. Tool positions are zero-based. Constructor/
protocol dispatch and file-level fallback imports require direct call-site inspection.

| Changed symbol | Actual references and required coverage |
|---|---|
| get_screener |9: run_pipeline factory and existing factory tests/imports; preserve keys/selection/none, add actual transport routing for both backend classes |
| GeminiFlashScreener.screen |2 direct method tests plus CandidateScreener protocol dispatch in run_pipeline; valid ranking, empty input, strict damaged body/batch/score controls |
| JevScreener.screen_one |1: JevScreener.screen; preserve valid explicit legacy diagnostic and refuse missing/clamped/coerced/current-wire mismatches |
| JevScreener.screen |Factory/class and protocol dispatch; validate batch/top_k before any candidate's request |
| Both _default_transport methods |Constructor-selected upstream boundaries; bounded read through real HTTP stream contract, no remote call during tests |
| ScreenedCandidate.__post_init__ |Constructor is dynamic;12 class references include both real decoders, existing validation/funnel mocks; original numeric ranking remains unchanged |
| _build_and_run |13: CLI/public alias and shared-builder tests; preserve regular paths, test guarded early refusal and explicit screener construction before model work |
| build_and_run |6 including durable_workflow import/step and test imports; signature extension optional keyword-only, complete durable/shared-builder regression coverage |
| run_pipeline |172 including CLI/durable/programmatic/episode/checkpoint/render/review tests; signature unchanged, receives existing screener object or unchanged ordinary string/none |

_run_pipeline_step has one direct workflow reference; its public alias use is indirect.
No durable/event schema, model/rubric policy, fixture/golden or enforcement edit is planned.
Complete affected scorer/factory/billing/pipeline/durable suites, then exact full gate covers
the broader unchanged run_pipeline contracts. No transport callback grants owner authority.

## Exhaustive Refusal Coverage Extension

First whole-caller diagnostic reproduced two uncovered-guard failures. The guard depends
on an injected Python transport and cannot be exercised through CLI argv alone. Two actual
supplementary Serena queries each found one definition and zero direct references for
test_every_refusal_in_the_source_has_a_case and
test_the_case_table_is_bound_bidirectionally_to_every_preflight_refusal. Pytest discovery
is their dynamic caller. Raw pre-edit record: screener-refusal-cases-before-map.json.
Add a separately executed transport case table to both exhaustive sets; preserve every
existing assertion and CLI case, bidirectional matching, and no-input-work assertions.
Do not classify a reachable Python guard as unreachable or hide its AST raise.

## SG2 Constructor Correction

Actual supplemental LSP mapping at879b02f45e12fc8d3f1513fc8ecb7067f2c6c3df is preserved
in screener-transport-identity-before-map.json. Both __init__ definitions are found with
zero direct references: invocation through the class is dynamic. GeminiFlashScreener has17
class references and JevScreener10, including the unchanged get_screener constructor calls
and direct controls in both screener test modules. Existing factory/valid/empty/missing-key
tests cover None and ordinary callable paths. Add an actual factory identity and decoding
test for a false-valued callable for each backend; assert identity before execution so the
red regression cannot accidentally reach remote HTTP. Change only the two constructor
fallback expressions. No model, request, score, builder or durable signature changes.
