# Specification: Content-Type Profiles (Task T4.5, ADR D-265)

## 1. Overview
This specification establishes genre-specific content-type profiles in HawEdit. Each profile configures editorial defaults appropriate for the source footage genre, spanning minimum clip duration, caption styling, punch-in pacing, and camera push-in dynamics.

## 2. Requirements & Acceptance Criteria (EARS)

### Criterion 1: Profile Retrieval and Enum Parsing
- **WHEN** `get_content_type_profile(content_type)` is called with a valid `ContentType` enum, string (case-insensitive), or `None`,
- **THE** system SHALL return the corresponding `ContentTypeProfile`, defaulting to `ContentType.PODCAST` when `None` is provided, and raising `ValueError` naming valid choices for unknown strings.

### Criterion 2: Editorial Constants by Profile
- **WHEN** a profile is retrieved for:
  - `podcast`: `min_clip_ms` SHALL be 30,000, `caption_style` SHALL be `CaptionStyle.POPUP`, `punch_in_cadence_ms` SHALL be 4,000, `eased_push` SHALL be True, `target_face_height_share` SHALL be 0.15.
  - `interview`: `min_clip_ms` SHALL be 25,000, `caption_style` SHALL be `CaptionStyle.POPUP`, `punch_in_cadence_ms` SHALL be 3,000, `eased_push` SHALL be True, `target_face_height_share` SHALL be 0.15.
  - `news`: `min_clip_ms` SHALL be 15,000, `caption_style` SHALL be `CaptionStyle.POPUP`, `punch_in_cadence_ms` SHALL be 0 (disabled), `eased_push` SHALL be False, `target_face_height_share` SHALL be 0.18.
  - `social`: `min_clip_ms` SHALL be 15,000, `caption_style` SHALL be `CaptionStyle.WORD_HIGHLIGHT`, `punch_in_cadence_ms` SHALL be 2,500, `eased_push` SHALL be True, `target_face_height_share` SHALL be 0.15.

### Criterion 3: CLI Flag & Precedence
- **WHEN** `--content-type` is supplied on the CLI,
- **THE** argument parser SHALL parse it into `args.content_type`, forwarding it to `run_pipeline`.
- **WHEN** an explicit argument (e.g. `--caption-style`, `--min-clip-seconds`) is also supplied,
- **THE** explicit argument SHALL override the profile default.
