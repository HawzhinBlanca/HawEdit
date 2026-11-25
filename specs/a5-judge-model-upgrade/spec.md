# Spec — Judge model current (a5-judge-model-upgrade)

EARS acceptance criteria (`tests/test_judge.py`, `tests/test_registry.py`, `tests/test_gemini.py`, `tests/test_credentials.py`, `tests/test_path_a.py`).

- **AC1** WHEN `KURDISH_EDITORIAL_JUDGE` and `JUDGE_SHADOW` are imported from `hawedit.judge`, THE system SHALL pin a non-deprecated current Gemini Pro-tier ID (`gemini-4-argon` or owner-selected `gemini-4-carbon`) as `KURDISH_EDITORIAL_JUDGE` and a valid routable/testable preview ID (`gemini-3.1-pro-preview` or `gemini-4-carbon`) as `JUDGE_SHADOW` ("evaluated, not routed").
  `test_judge_and_shadow_constants_use_current_gemini_models`

- **AC2** WHEN `PathADiscovery`, `GeminiJudge`, `VertexGeminiJudge`, `pipeline.py`, `credentials.py`, `setup_panel.py`, or `smoke.py` select the default editorial judge, THE modules SHALL reference `KURDISH_EDITORIAL_JUDGE` rather than hardcoded `"gemini-2.5-pro"` strings.
  `test_no_hardcoded_deprecated_gemini_25_pro_in_runtime_paths`

- **AC3** WHEN `hawedit.registry.resolve` resolves `KURDISH_EDITORIAL_JUDGE` and `JUDGE_SHADOW`, THE registry SHALL mark the incumbent `routable=True`, keep the shadow `routable=False`, preserve exact 1-to-1 §7 blueprint-cell mapping with explicit ADR divergence traceability (`D-339`), and align `USD_PER_MILLION_TOKENS` / pricing metadata cleanly.
  `test_judge_is_pinned_and_shadow_is_not_routable`, `test_registry_contains_nothing_that_is_not_in_section_7`, `test_registry_omits_nothing_that_is_in_section_7`

- **AC4** WHEN the Stage 4 judge test suite (`tests/test_judge.py`, `tests/test_gemini.py`, `tests/test_judge_calibration.py`, `tests/test_promotion.py`, `tests/test_editorial_bench.py`, `tests/test_editorial_acceptance.py`, `tests/test_credentials.py`) runs after updating to `D-339`, ALL assertions SHALL pass without skips or mocks of the upgraded routing guard.
  `test_shadow_verdict_cannot_bypass_routing_guard`

- **AC5** WHEN `GEMINI_API_KEY` has confirmed billing (`BLOCKED.md #3`), running a single billed smoke / judge verdict via `python -m hawedit.smoke` on an excerpt SHALL return HTTP 200 structured `JudgeVerdict` with Sorani `title_ckb` and record the cost and latency in `evidence/`.
  *(Live verification gate — gated on `[HAWA]` paid-key confirmation.)*
