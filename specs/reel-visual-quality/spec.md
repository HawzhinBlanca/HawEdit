# Spec — Reel Visual Quality & Framing Gate

## Acceptance Criteria (EARS Format)

- **CRIT-1 (Evaluator Strict Fail-Stop):**
  WHEN `GeminiStoryEvaluator` receives a JSON response from Gemini lacking any required story evaluation field (`virality_score`, `headline_kurdish`, `summary_kurdish`, or per-sentence `importance_score`/`keep`),
  THE system SHALL raise `StoryCondensationError` immediately without silent fallback to default values.

- **CRIT-2 (Per-Shot Adaptive Framing):**
  WHEN a video clip contains camera cuts defined by `shot_cuts_ms`,
  THE system SHALL compute vertical face height and position per shot interval and update the crop window dynamically via `sendcmd` at shot cut boundaries, adhering to `MAX_VERTICAL_ZOOM = 1.5`.

- **CRIT-3 (SanityGate Framing Quality Floor):**
  WHEN `SanityGate.check_face_presence` audits rendered vertical shots,
  THE system SHALL measure face height share and vertical placement per shot, and SHALL fail if face height share is below the minimum threshold (0.08) or if eye position falls outside the composition line bounds.

- **CRIT-4 (Caption Safe Zone & Hook Styling):**
  WHEN `build_ass` generates subtitle tracks for viral reels,
  THE system SHALL place kinetic pop dialogue subtitles at chest level (`margin_v` >= 480px, avoiding the bottom 25% UI danger zone) and render hook banners with high-contrast styling.
