# Research: Content-Type Profiles (Task T4.5, ADR D-265)

## 1. Problem & Context
From `specs/pro-grade-program/tasks.md` Task T4.5:
> **Task T4.5 (P2): Content-type profile.**
> `--content-type {podcast, interview, news, social}` set by Hawa per source; drives thresholds, caption style, punch-in cadence, tightening default. ADR.
> *Why:* No mode anywhere; ep29 is a podcast, KAAE material is not.

Historically, HawEdit applied identical constants across all inputs:
- Candidate minimum span: hardcoded `MIN_CANDIDATE_SPAN_MS = 30_000` (30s).
- Punch-in cadence: hardcoded `4_000` ms.
- Eased push-in: flag-driven or deliverable profile.
- Caption style: `CaptionStyle.POPUP` or `WORD_HIGHLIGHT`.
- Target face height share: hardcoded `0.15`.

For news broadcasts (e.g. KAAE news anchors), jump-cut punch-ins and 30-second minimum spans look unprofessional and inappropriate. For social reels, a 30s minimum span causes rejection of punchy 15s moments, and word-highlight karaoke captions are mandatory for viral engagement.

## 2. Genre Profile Mapping
| Content Type | Min Span | Caption Style | Punch-in Cadence | Eased Push | Face Share | Description |
|---|---|---|---|---|---|---|
| `podcast` | 30s | `POPUP` | 4,000 ms | True | 0.15 | Relaxed, contemplative dialogue (ep29 standard) |
| `interview` | 25s | `POPUP` | 3,000 ms | True | 0.15 | Dynamic back-and-forth Q&A exchanges |
| `news` | 15s | `POPUP` | 0 (disabled) | False | 0.18 | Formal anchor reporting; locked camera; zero punch-ins |
| `social` | 15s | `WORD_HIGHLIGHT` | 2,500 ms | True | 0.15 | High-energy TikTok/Reel clips; fast cuts; animated karaoke |

## 3. Architecture & Design
- Create `src/hawedit/content_type.py`:
  - `ContentType(str, Enum)`: `podcast`, `interview`, `news`, `social`.
  - `ContentTypeProfile`: immutable dataclass containing editorial thresholds.
  - `CONTENT_TYPE_PROFILES`: dictionary mapping each `ContentType` to its profile.
  - `get_content_type_profile(content_type)`: safe parser with default fallback and descriptive validation errors.
- Wire into `src/hawedit/pipeline.py`:
  - `--content-type` CLI argument in `build_parser`.
  - `content_type` parameter in `run_pipeline`.
  - Intelligently applies profile defaults while allowing explicit CLI overrides to take precedence.
