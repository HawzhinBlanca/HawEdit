# Specification — Cover Frame and Title Variants (Task T4.10)

## Ubiquitous Language
- **Cover Frame**: A single representative video frame chosen as the static preview/thumbnail (`cover.png`) for social platforms.
- **Face Share**: The ratio of detected face height to total frame height ($h_{face} / h_{frame}$).
- **Sharpness Score**: The variance of the Laplacian operator computed over the detected face region ($\sigma^2(\nabla^2 I_{face})$).
- **Eyes-Open Heuristic**: Detection of eye regions in the upper half of the face box using Haar cascades, penalising closed/blinking eyes.
- **Title Variants**: Three distinct Kurdish Sorani title options for A/B testing social engagement.

## Acceptance Criteria (EARS Format)

### AC-1: Cover Frame Selection Heuristic
- **WHEN** `select_cover_frame` evaluates candidate video frames,
- **THE** system SHALL score each candidate using:
  $$\text{score} = (\text{face\_share} \times 100.0) \times \ln(1 + \max(1.0, \text{sharpness})) \times \text{eye\_multiplier}$$
  where $\text{eye\_multiplier} = 1.0$ if $\ge 2$ eyes are detected, $0.6$ if $1$ eye is detected, and $0.1$ if $0$ eyes are detected.

### AC-2: Output Image Generation
- **WHEN** the optimal cover frame candidate is selected,
- **THE** system SHALL extract and write the exact frame at the selected timestamp as an image file (`cover.png`) matching the video's vertical resolution.

### AC-3: Kurdish Title Variants
- **WHEN** generating title variants for a clip,
- **THE** system SHALL output a sequence of 3 non-empty Kurdish Sorani strings representing:
  1. High-impact primary hook
  2. Question/inquiry format
  3. Declarative/quotation format.

### AC-4: Contract Serialization
- **WHEN** serializing `Clip.output` to JSON via `to_dict()`,
- **THE** system SHALL include `"title_variants_ckb"` and `"cover_frame_ms"`, and deserialize them faithfully in `from_dict()`.

### AC-5: Delivery Bundle Integration & Reconciliation
- **WHEN** `publish_delivery_bundle` is executed with a generated cover image,
- **THE** system SHALL copy/write `cover.png` into the deliverable output directory.
- **WHEN** `reconcile_delivery` runs on a clip with `output.cover_frame_ms`,
- **THE** system SHALL verify that $0 \le \text{cover\_frame\_ms} \le \text{clip duration}$.
