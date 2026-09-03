# Specification: Visual-Variety-Aware Selection (Task T4.6)

## 1. Overview
This specification defines the visual-variety-aware candidate tiebreaker for HawEdit (`specs/pro-grade-program/tasks.md` Task T4.6). When multiple candidate clips pass §2 editorial criteria and tie on core editorial scores, the system selects the clip with higher visual variety (source camera cuts per second), resolving the flat footage bias documented in `HANDOFF.md` §5 while remaining strictly behind an opt-in flag.

## 2. Requirements & Acceptance Criteria (EARS)

### Criterion 1: Visual Variety Metric Calculation
- **WHEN** `calculate_visual_variety(span, shot_cuts_ms)` is called with a time span `(start_ms, end_ms)` and a sequence of source cut timestamps,
- **THE** system SHALL count all source cuts strictly within the interior `start_ms < cut < end_ms` and divide by the span duration in seconds, returning `cuts / duration_s` (or `0.0` for non-positive durations).

### Criterion 2: Default Tiebreaking Preserved
- **WHEN** `--visual-variety` is omitted (default `visual_variety=False`),
- **THE** system SHALL rank shippable candidates solely on `(hook_score, payoff_strength, ends_on_a_beat)`, preserving existing deterministic selection order.

### Criterion 3: Visual Variety Tiebreak Under Flag
- **WHEN** `--visual-variety` is supplied (or `visual_variety=True`),
- **THE** system SHALL include the visual variety metric as the fourth ranking component `(hook_score, payoff_strength, ends_on_a_beat, visual_variety)` so that candidates tying on editorial scores are broken in favor of the candidate with more camera angle changes.

### Criterion 4: CLI Parsing & Pipeline Forwarding
- **WHEN** `hawedit.pipeline` is invoked with `--visual-variety`,
- **THE** argument parser SHALL parse `args.visual_variety = True` and forward it to `run_pipeline`.
