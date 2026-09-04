# Specification — Episode Plan: N Clips Per Run (Task T4.1)

## Acceptance Criteria

- **AC-1:** WHEN candidates are evaluated for an episode plan, THE system SHALL select up to $N$ shippable winner clips in ranked order of composite editorial score.
- **AC-2:** WHEN evaluating candidates, THE system SHALL refuse any candidate that temporally overlaps with any already selected clip.
- **AC-3:** WHEN evaluating candidates, THE system SHALL refuse any candidate that is separated from any already selected clip by less than `min_separation_ms` (default 15,000 ms).
- **AC-4:** WHEN evaluating candidates, THE system SHALL compute lexical similarity (normalized Kurdish Sorani word overlap) and SHALL reject any candidate exceeding `max_text_similarity` (default 0.50) against any already selected clip.
- **AC-5:** WHEN an episode plan is generated, THE system SHALL emit an `EpisodeManifest` (`episode.json`) containing metadata, total clips count, total duration, total estimated cost, and an ordered list of `EpisodeClipSummary` records.
- **AC-6:** WHEN `reconcile_episode_manifest` is executed, THE system SHALL verify that every clip in the manifest exists on disk, contains valid delivery sidecars, and that no two delivered clips have overlapping time spans.
- **AC-7:** WHEN cost exceeds `cost_cap_usd`, THE system SHALL halt further candidate judging while retaining all valid clips selected within budget.
