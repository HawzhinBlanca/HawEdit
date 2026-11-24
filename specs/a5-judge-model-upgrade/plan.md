# Plan — Judge model current (a5-judge-model-upgrade)

Read [`research.md`](./research.md) and [`spec.md`](./spec.md) first. Proposed ADR: **D-339**.

## Approach

1. **Recommend upgrading `KURDISH_EDITORIAL_JUDGE` & `JUDGE_SHADOW` before 2026-12-01 (subject to owner selection):**
   - **Recommended:** `KURDISH_EDITORIAL_JUDGE = "gemini-4-argon"` (efficient frontier Pro-tier reasoning, `$2.00/$10.00` through Nov 30, `$4.00/$20.00` from Dec 1, live in `/v1beta/models` and `:countTokens`), with `JUDGE_SHADOW = "gemini-4-carbon"` (or `"gemini-3.1-pro-preview"` if keeping flagship/preview split — both verified live; replacing dead `gemini-3.1-pro` which HTTP-404s). Alternative if owner wants maximum reasoning immediately: `KURDISH_EDITORIAL_JUDGE = "gemini-4-carbon"`.
   - Record cost metadata accurately in `judge.py` (`USD_PER_MILLION_TOKENS` and ADR `D-339` noting Dec 1 `$4/$20` rate transition).
2. **Eliminate hardcoded `"gemini-2.5-pro"` runtime literals:**
   - Replace literal defaults in `path_a.py:141`, `pipeline.py:3587`, and `credentials.py:577` with `KURDISH_EDITORIAL_JUDGE`.
   - Update operator diagnostics in `pipeline.py:793`, `setup_panel.py:81-84`, and `smoke.py:17,194`.
3. **Keep `registry.py` ↔ `BLUEPRINT.md §7` honest and passing (`tests/test_registry.py`):**
   - Update `REGISTRY` entries cleanly so `model_id` becomes the new `KURDISH_EDITORIAL_JUDGE` / `JUDGE_SHADOW` while retaining `blueprint_model_cell` (`"gemini-2.5-pro, pinned"` and `"gemini-3.1-pro"`) plus a documented `MODEL_DIVERGENCES` constant tied to `D-339` (frozen `BLUEPRINT.md` untouched).
   - Update `tests/test_registry.py:247-248` to `resolve(KURDISH_EDITORIAL_JUDGE)` and `resolve(JUDGE_SHADOW)`.
   - Also allow optional Gemini 3/4 `thinkingConfig` passthrough if needed later without breaking `PRO_TIER_TOKEN_CEILING` or JSON schema parsing in `gemini.py`.
4. **Update judge/credential tests & run 1 live smoke verdict:**
   - Migrate direct `"gemini-2.5-pro"` / `"gemini-3.1-pro"` routing expectations in `tests/test_gemini.py`, `tests/test_judge.py`, `tests/test_credentials.py`, `tests/test_setup_panel.py`, `tests/test_studio_billing.py`, `tests/test_path_a.py`, `tests/test_clip.py`, `tests/test_promotion.py`, `tests/test_pipeline.py:5999` to use `KURDISH_EDITORIAL_JUDGE` / `JUDGE_SHADOW` (leaving historical fixture tests cleanly parameterized or untouched where purely structural).
   - Once owner confirms paid-tier billing on `GEMINI_API_KEY` (`BLOCKED.md #3`), execute `hawedit.smoke` (1 real verdict) and record cost + response JSON + latency in `evidence/`.

## Files and symbols

| File | Symbol | Planned Change |
|---|---|---|
| `src/hawedit/judge.py` | `KURDISH_EDITORIAL_JUDGE` (`:92`), `JUDGE_SHADOW` (`:93`), `USD_PER_MILLION_TOKENS` (`:114`) | Update constants + docstrings to `D-339` target models & current pricing |
| `src/hawedit/path_a.py` | `PathADiscovery.__init__` (`:141`) | Default `model_id = KURDISH_EDITORIAL_JUDGE` instead of literal |
| `src/hawedit/pipeline.py` | `_STAGE_4_JUDGE` (`:793`), `_run_from_args`/editorial call (`:3587`) | Replace literal `"gemini-2.5-pro"` fallback and help text with `KURDISH_EDITORIAL_JUDGE` |
| `src/hawedit/credentials.py`, `setup_panel.py`, `smoke.py` | `_PINNED_JUDGE` (`:577`), `_SLOTS` (`:81-84`), `main` (`:194`) | Reference `KURDISH_EDITORIAL_JUDGE` cleanly |
| `src/hawedit/registry.py`, `tests/test_registry.py` | `_ENTRIES` (`:298-322`), `test_judge_is_pinned_and_shadow_is_not_routable` (`:245-248`) | Move `model_id`s to `D-339` models while preserving `blueprint_model_cell` §7 mapping |
| `tests/test_gemini.py`, `test_judge.py`, `test_credentials.py`, `test_setup_panel.py`, `test_studio_billing.py`, `test_path_a.py`, `test_clip.py`, `test_promotion.py`, `test_pipeline.py` | Judge model expectations | Reference `KURDISH_EDITORIAL_JUDGE` / `JUDGE_SHADOW` and verify AC1–AC4 |
| `DECISIONS.md`, `BLOCKED.md`, `PROGRESS.md` | New `D-339`, `#3` update | Record deprecation evidence & live verdict outcome |

## Divergence and Risks

- **Explicit §4/§7 divergence (`D-339`):** Supersedes §4/§7's `gemini-2.5-pro` pin and `gemini-3.1-pro` shadow ID because `2.5-pro` retires/auto-routes Dec 1 and `3.1-pro` HTTP-404s. `BLUEPRINT.md` itself stays frozen.
- **Sorani calibration risk:** Moving to a newer Pro model without running a ≥20-item blind comparison (`MIN_REGRESSION_ITEMS`) assumes at least parity with 2.5 Pro; **necessitated by vendor deprecation on Dec 1** (requests to `2.5-pro` silently become `3.8-flash` on Dec 1 otherwise!). Once reels flow, shadow vs incumbent regression remains tracked via `editorial_bench.py`.
- **Paid key #3:** Live verdict (`AC5`) cannot pass until billing is active on `GEMINI_API_KEY`.

## `[HAWA]` Owner Actions Folded Into This Approval

1. Confirm target judge pair for **D-339**: **`gemini-4-argon` (incumbent) + `gemini-4-carbon` (or `gemini-3.1-pro-preview`) shadow**, OR **`gemini-4-carbon` incumbent**.
2. Confirm paid-tier billing is active on `GEMINI_API_KEY` (`…IEu4`, `BLOCKED.md #3`) and authorize 1 live billed `hawedit.smoke` / Stage 4 call + Phase A episode runs.

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"
