# Specification — Cold-Open Assembly (Task T4.9)

## Acceptance Criteria (EARS Format)

### AC-1: Cold-Open Timeline Assembly
WHEN `assemble_cold_open` is called with setup sentences and a payoff sentence from distinct timeline positions, THE system SHALL assemble the payoff sentence first as the 0–3s hook, followed by the setup sentences, re-offsetting all word timestamps continuously starting at $t=0$ while ensuring complete sentences (Kurdish invariant #2).

### AC-2: Assembled Media Splicing and Rendering
WHEN `render_assembled_reel` is invoked with source video, THE system SHALL:
- Extract and splice the participating media intervals in cold-open order.
- Apply 9:16 vertical crop and reframe.
- Generate and burn ASS subtitles synchronized exactly to the assembled timeline.
- Plan and apply re-timed punch-ins on assembled sentence boundaries.
- Encode the deliverable MP4 to the exact assembled duration.

### AC-3: Frame-Grounded Assembly Judging
WHEN `judge_assembled_reel_multimodal` is executed, THE system SHALL extract representative keyframes directly from the assembled render MP4 and score the assembly as a unified multi-modal piece.

### AC-4: Misleading-Edit Risk Gate
WHEN the judge evaluates the assembled reel, THE system SHALL gate `verdict.misleading_edit_risk <= MAX_MISLEADING_EDIT_RISK` (0.10). If the non-linear splice introduces misleading context or distorts speaker meaning, THE system SHALL raise `EditorialBelowThreshold`.
