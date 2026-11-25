# Tasks ledger — a5-judge-model-upgrade
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  ADR D-339; upgrade KURDISH_EDITORIAL_JUDGE and JUDGE_SHADOW and remove hardcoded 2.5-pro runtime defaults   (tests: test_judge_and_shadow_constants_use_current_gemini_models, test_no_hardcoded_deprecated_gemini_25_pro_in_runtime_paths)
- [x] T2  Align §7 registry entries, routing guards, and Stage 4 unit test suite cleanly   (tests: test_judge_is_pinned_and_shadow_is_not_routable, test_registry_contains_nothing_that_is_not_in_section_7, test_registry_omits_nothing_that_is_in_section_7, test_shadow_verdict_cannot_bypass_routing_guard)
- [x] T3  Execute 1 live billed Stage 4 verdict (after paid key #3 confirmation) and record evidence   (tests: test_shadow_verdict_cannot_bypass_routing_guard)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh on integration branch)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Live Stage 4 verdict recorded in evidence/ with latency and cost
