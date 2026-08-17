# Confidential Vertex acceptance kit

Date: 2026-08-17

Scope: autonomous engineering evidence for HK-7, not a live confidential-client acceptance.

## Implemented boundary

`src/hawedit/vertex_acceptance.py` prepares a packet without cloud transport. The private source
manifest binds exact authorised video, normalized transcript, candidate request, retained
zero-data-retention policy, approved Vertex project/location/model, expected ADC identity, billing
account and owner token/cost limits. Paths are contained below one real private root; linked,
changed, malformed, non-video, duration-mismatched, non-normalized, unbounded or coercive input is
refused. The published preparation packet contains hashes and an unset approval template, not
client content.

Execution recomputes those inputs, verifies an OpenSSH detached signature, refreshes ADC, requires
the exact ADC project/type/principal, checks Cloud Billing and `aiplatform.googleapis.com` live,
extracts 1–20 exact-span frames in an owned temporary workspace, and creates a write-once attempt
receipt before any model request. `GeminiJudge.judge_with_count` performs one authoritative
`countTokens`, applies both §3 and signed ceilings, and makes no more than one non-retried
`generateContent` attempt. The receipt survives every outcome and prevents replay.

The final evidence intentionally excludes access tokens, billing-account names, full transcript
text, visual descriptions, raw frame bytes, retained policy text and generated Kurdish editorial
copy. It records their SHA-256 bindings, route and redacted environment identity, exact counted
tokens, estimated input cost, one paid-attempt count, numeric verdict fields and signature identity.

## Automated evidence

On hawapc01, Windows, CPython 3.12.10, before the final commit:

- `tests/test_vertex_acceptance.py` + `tests/test_gemini.py`: **113 passed**, zero skips.
- Vertex/Gemini/judge/Path A/pipeline/smoke/keyframe/transcript/claims/WSL-VEX integration
  slice: **717 passed**, zero skips.
- Ruff check and format: clean for both source and test files.
- mypy `--strict --no-incremental`: clean for `vertex_acceptance.py` and `gemini.py`.
- A recording transport through the real `VertexGeminiJudge` boundary observed exactly
  `countTokens`, then `generateContent`, with ADC only in the bearer header.
- Adversarial regressions cover schema coercion, path escape, hardlinks, content drift, unsigned or
  false human approval, text/clip alignment drift, pre-existing operator output, stale/future live
  checks, wrong ADC project/type/principal, disabled billing/API, wrong billing account,
  ambiguous-call replay, protected Windows ACLs, nested private-frame cleanup and public-evidence
  secret/content absence.

The preceding exact SHA `60b4d1d47e30a50d18af2f503cabd05bbaab1b81` passed both hosted
`python-312-compat` and canonical `gate` jobs in Actions run `31988589122`. The Vertex delta still
requires its own clean canonical gate and exact-SHA hosted checks before it is accepted.

## Honest shortfall

Completed paid confidential studies on disk: **0**.

HawEdit has no approved paid Vertex project, usable ADC, matching authorised 13-second sample,
signed contractual ZDR confirmation or owner spend approval in this repository. Code and tests do
not substitute for those inputs. `BLOCKED.md` #3 and #19 remain live, and the generated template is
not human acceptance.
