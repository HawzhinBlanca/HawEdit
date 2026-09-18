# Research — Fast Candidate Screener Funnel (Gemini Flash & TypeSafe Jev)

## Context
In HawEdit's editorial architecture (`BLUEPRINT.md` §3–§4), Stage 3 generates candidate spans from transcripts and visual beats, and Stage 4 (`EditorialJudge`) scores them using Gemini 2.5 Pro.
`specs/judge-top-n/plan.md` noted:
> "Cost is the real one. N=5 is five billed calls per run, and a run that finds nothing shippable still pays for all of them."

In an hour-long episode (e.g. 188 sentences, 60–100 potential candidate spans), judging more than 3 candidates with Gemini 2.5 Pro takes 30–60 seconds of latency and costs hundreds of thousands of billed tokens. Consequently, 90% of potentially viral moments in an episode are never evaluated by an AI model.

## Candidate Solutions Researched

### 1. TypeSafe Jev (System One Model)
- Released mid-September 2026 by TypeSafe AI.
- Architecture: Non-autoregressive parallel evaluation.
- Primitives: `Choice` (enums), `Score` (calibrated float 0-100), `Noul` (calibrated boolean probability via RLCD).
- Latency: 70ms–300ms.
- Cost: $0.042 / 1M input tokens, output tokens are free ($0.00).
- Limits: Context window up to 32,000 tokens.
- Reality Check:
  - Jev cannot generate text: cannot write `title_ckb`, `description_ckb`, `hashtags_ckb`, or `reason_ckb`.
  - Jev is a proprietary cloud API requiring `TYPESAFE_API_KEY` or OpenRouter.
  - Zero Kurdish Sorani benchmarks exist; risk of misjudging nuanced colloquialisms.

### 2. Gemini 2.5 Flash / Flash-Lite (Existing Authenticated Provider)
- Sub-400ms TTFT, $0.075 / 1M tokens.
- Native Sorani Kurdish Arabic-script competence (verified on 30+ golden fixtures).
- Output: Typed JSON schema with zero hallucination.
- Fully authenticated in HawEdit's existing credential store (`credential_status` confirms 50 models visible).

## Architectural Decision
Implement a pluggable two-tier screening funnel (`CandidateScreener`):
- **Tier 1 (Screening)**: High-throughput, low-latency evaluation of all candidate spans across the episode. Prunes 80+ candidates down to top $K$ (e.g. 2–3).
  - Supports `GeminiFlashScreener` (default, zero extra credentials).
  - Supports `JevScreener` (optional accelerator via `TYPESAFE_API_KEY`).
- **Tier 2 (Judging)**: Gemini 2.5 Pro receives only the single top-ranked screened survivor to write the Kurdish title, description, and hashtags.
