# Research — Judge model current (a5-judge-model-upgrade)

Date: 2026-11-18. Host: `HawaPC01`, commit `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf`. Serena MCP was unavailable; callers mapped via `rg`.

## 1. Verified Google Gemini API Deprecation & Active Model Status (2026-11-18)

Checked directly against official Google documentation and live API probes (read-only `/v1beta/models` and free `:countTokens`; no billed `generateContent` executed):

- **Official deprecations (`ai.google.dev/gemini-api/docs/deprecations` & `/docs/models`, `cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions`):**
  - `gemini-2.5-pro` (released June 17, 2025) is **deprecated**, removed from Google AI Studio, retired on Vertex AI effective **2026-10-20**, and **effective 2026-12-01 all Gemini Developer API requests sent to `gemini-2.5-pro` automatically route to `gemini-3.8-flash`** (and bill at `3.8-flash` rates).
- **Live probe on HawaPC01 with `GEMINI_API_KEY` (`…IEu4`):**

| Model ID | Doc Role / Availability | Pricing per 1M tokens (input / output) | Live `/v1beta/models` + `:countTokens` |
|---|---|---|---|
| `gemini-2.5-pro` (current `KURDISH_EDITORIAL_JUDGE`) | Deprecated; Vertex retired `2026-10-20`; API auto-routes to `3.8-flash` `2026-12-01` | — | Present now; silently changes behavior Dec 1 |
| `gemini-3.1-pro` (current `JUDGE_SHADOW`) | Invalid un-suffixed ID | — | **HTTP 404** on `:countTokens` |
| `gemini-4-argon` | Current efficient frontier reasoning Pro-class (released `2026-10-13`, Paid tier) | `$2.00 / $10.00` through Nov 30; `$4.00 / $20.00` from Dec 1 | Visible + `:countTokens` **HTTP 200** |
| `gemini-4-carbon` | Current flagship maximum reasoning Pro-class (released `2026-11-10`, Paid tier) | `$2.00 / $10.00` through Nov 30; `$4.00 / $20.00` from Dec 1 | Visible + `:countTokens` **HTTP 200** |
| `gemini-3.1-pro-preview` | Reasoning preview model (released `2026-02-19`, Paid tier <= 200k) | `$2.00 / $12.00` | Visible + `:countTokens` **HTTP 200** |
| `gemini-3.8-flash` | Flash tier (released `2026-09-02`, Free tier available) | `$0.75 / $3.75` through Dec 31 | Visible + `:countTokens` **HTTP 200** |

## 2. Hardcoded Pins & Registry Mechanics in HawEdit

1. **`KURDISH_EDITORIAL_JUDGE` & `JUDGE_SHADOW` (`src/hawedit/judge.py:92-93`):**
   - `KURDISH_EDITORIAL_JUDGE = "gemini-2.5-pro"` and `JUDGE_SHADOW = "gemini-3.1-pro"` (which 404s on live `:countTokens`).
   - Hardcoded `"gemini-2.5-pro"` literals bypass `KURDISH_EDITORIAL_JUDGE` in `src/hawedit/path_a.py:141`, `src/hawedit/pipeline.py:3587` (plus help string `:793`), `src/hawedit/credentials.py:577` (`_PINNED_JUDGE`), `src/hawedit/setup_panel.py:81-84`, and `src/hawedit/smoke.py:17,194`.
2. **Blueprint §7 registry parity (`src/hawedit/registry.py:298-322`, `tests/test_registry.py:75-94, 245-248, 355-358`):**
   - `BLUEPRINT.md` is frozen ("diverging needs an ADR in `DECISIONS.md`").
   - `tests/test_registry.py` asserts exact 1-to-1 equality between `REGISTRY[...].blueprint_model_cell` and `BLUEPRINT.md §7`'s markdown table (`"gemini-2.5-pro, pinned"` and `"gemini-3.1-pro"`), and `test_judge_is_pinned_and_shadow_is_not_routable` (`:247-248`) currently hardcodes `resolve("gemini-2.5-pro")` and `resolve("gemini-3.1-pro")`.
   - Updating `ModelEntry.model_id` (while preserving `blueprint_model_cell` per §7 table cell + recording the ADR **D-339** override table cleanly in `registry.py` & updating `test_registry.py` to check `KURDISH_EDITORIAL_JUDGE` / `JUDGE_SHADOW`) keeps §7 invariant audits strict and honest without editing frozen `BLUEPRINT.md`.
3. **Billing / paid tier (`BLOCKED.md #3`):**
   - `hawedit.credentials --check` confirms `GEMINI_API_KEY: …IEu4` is stored and sees 50 models, but paid `generateContent` billing was NOT tested in Round 1 (`BLOCKED.md #3` historically saw HTTP 429 `free_tier_requests, limit: 0`). Owner confirmation is needed before spending billed calls in `hawedit.smoke` / live verification.

Answers to: `BLUEPRINT.md` §3, §4, §7; `BLOCKED.md` #3; proposes **D-339**.
