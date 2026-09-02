# Specification — Human Review is a Record, Not a Flag (`specs/qc-record`)

## Acceptance Criteria (EARS Format)

- **AC-1 (QC Record Validation)**:
  WHEN a `QcRecord` is created or parsed,
  THE system SHALL require `reviewer` to be a non-empty string, `reviewed_at` to be a valid ISO-8601 UTC timestamp, `mp4_sha256` to be a 64-character lowercase hex string, `seconds_watched` to be > 0, and `verdict` to be a non-empty string;
  OTHERWISE, THE system SHALL raise a `ValueError` with descriptive reason.

- **AC-2 (Qc Dataclass Invariant)**:
  WHEN a `Qc` instance has `human_reviewed == True`,
  THE `Qc` dataclass SHALL require `reviewed_by` to be a non-empty string, `reviewed_at` to be an ISO-8601 timestamp string, and `reviewed_sha256` to be a 64-character hex string;
  IF ANY of these fields are missing or empty,
  THE system SHALL raise a `ValueError` stating that `human_reviewed` requires matching review record fields.

- **AC-3 (CLI Flag Replacement)**:
  WHEN the pipeline CLI is executed,
  THE CLI parser SHALL reject `--qc-pass` as an unrecognized argument;
  WHEN `--qc-record <path_or_json>` is supplied,
  THE CLI SHALL parse and validate the review record and instantiate `Qc` carrying `reviewed_by`, `reviewed_at`, and `reviewed_sha256`.

- **AC-4 (Reconciliation Gate Hash Binding)**:
  WHEN a delivery is reconciled via `reconcile_delivery`,
  IF `clip.qc` has `human_reviewed == True`,
  THE reconciliation gate SHALL verify that `clip.qc.reviewed_sha256` exactly matches `measurement.file.sha256`;
  IF the hashes do not match,
  THE gate SHALL raise `DeliveryRefused("qc_sha256_mismatch", expected=measurement.file.sha256, measured=clip.qc.reviewed_sha256)`.

- **AC-5 (Agent Tool Isolation)**:
  WHEN any agent tools in `hawedit` are registered,
  THE Policy Gate SHALL verify that no tool exposes the capability to fabricate or sign a human review record;
  AND no agent tool implementation SHALL construct a `QcRecord`.

- **AC-6 (Interactive Revision Attribution)**:
  WHEN an interactive revision is committed in `proposals.py`,
  THE system SHALL bind the human approver's name to `reviewed_by`, the commit timestamp to `reviewed_at`, and the freshly rendered revision MP4's SHA-256 to `reviewed_sha256`.
