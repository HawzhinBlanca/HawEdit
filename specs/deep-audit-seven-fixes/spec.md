# Acceptance criteria

- AC1 WHEN silence-only or explicit filler removal sees a meaningful prefix/repetition, THE system SHALL preserve spoken words unless restart removal is separately requested; prefix deletion SHALL additionally require an explicit truncation marker.
- AC2 WHEN an episode clip is shortened, THE summary SHALL use effective output duration and reconcile measured media while preserving source provenance bounds.
- AC3 WHEN source or temporal evidence is absent/undecodable/out-of-bounds, THE critic SHALL refuse all-clear; reported frame counts SHALL equal decoded observations and pipeline consumers SHALL enforce refusal.
- AC4 WHEN a moment occurs beyond word 4000, THE discovery prompt SHALL retain its sentence anchor and resolve model-selected indices from aligned source clocks.
- AC5 WHEN any media, alignment, model/prompt/voting input changes, THE cache SHALL not replay a result under the old identity; malformed or mismatched records SHALL never return candidates.
- AC6 WHEN opening-frame validation is enabled, THE whole-clip default face/speech presence floors SHALL remain in force for all tracked modes.
- AC7 WHEN current media root is configured, THE test tier SHALL run current pinned-source checks; legacy ep29 assertions SHALL remain available under the legacy profile, and tier/profile selection SHALL be visible.
