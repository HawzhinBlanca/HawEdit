# Research — Human Review is a Record, Not a Flag (`specs/qc-record`)

> Implementation research for Phase 1 Task T1.3 from `specs/pro-grade-program/tasks.md`
> Grounding on `src/hawedit/clip.py`, `src/hawedit/pipeline.py`, `src/hawedit/delivery.py`, `src/hawedit/proposals.py`, `src/hawedit/policy.py`.

## 1. Problem Statement & Audit Finding

In `specs/pro-grade-program/research.md` §5 (Row 4 of the 14-Row Register of Unverified Claims):
- **Contract Claim**: `qc.human_reviewed: true`.
- **Current Generation**: Set by passing `--qc-pass` on the CLI or `qc=Qc(auto_pass=True, flags=(), human_reviewed=True)` in Python.
- **Vulnerability**: Any shell or script can set `human_reviewed=true` with zero evidence that a human ever watched a single frame of the delivered MP4. There is no reviewer identity, no timestamp, no hash binding to the rendered media, and no record of seconds watched.
- **Threat 1**: Synthetic / unverified clips claim human editorial oversight when no human was present.

## 2. Target Contract Specification (Task T1.3)

1. **Retire `--qc-pass`**: The bare boolean flag `--qc-pass` is completely removed. Passing it is refused.
2. **Introduce `--qc-record <path_or_json>`**: Replaces `--qc-pass`. Accepts either a path to a JSON file or an inline JSON object containing:
   - `reviewer`: Non-empty string naming the human reviewer (e.g. `"Hawa"`).
   - `reviewed_at`: ISO 8601 UTC timestamp string.
   - `mp4_sha256`: 64-character lowercase hexadecimal SHA-256 digest of the rendered MP4.
   - `seconds_watched`: Positive number (`float | int > 0`) indicating how many seconds the reviewer actually watched.
   - `verdict`: Approval verdict string (e.g. `"pass"`, `"approved"`).
   - `notes`: Optional string containing reviewer comments/observations.
3. **Extend `Qc` Dataclass**:
   - Gains fields:
     - `reviewed_by: str | None = None`
     - `reviewed_at: str | None = None`
     - `reviewed_sha256: str | None = None`
   - Invariant: If `human_reviewed is True`, `reviewed_by` must be non-empty, `reviewed_at` must be valid ISO-8601, and `reviewed_sha256` must be a valid 64-char hex string. Any attempt to set `human_reviewed=True` without these fields raises `ValueError`.
4. **Reconciliation Gate Enforcement**:
   - When `reconcile_delivery` runs, if `clip.qc.human_reviewed` is True:
     - Reconcile `clip.qc.reviewed_sha256 == measurement.file.sha256`.
     - Reconcile `reviewed_at` does not precede the render completion timestamp.
     - Refuse with `DeliveryRefused("qc_sha256_mismatch", expected=..., measured=...)` on mismatch.
5. **Agent Surface Isolation**:
   - The agent tool surface (`policy.py`, `workflow_agent.py`, `agent.py`) must have zero capability to write, create, or fabricate a `QcRecord`.
   - Verified by `test_the_agent_surface_cannot_write_a_review_record`.

## 3. Real Code Surface Mapping

- `src/hawedit/clip.py`:
  - `class Qc`: Add `reviewed_by`, `reviewed_at`, `reviewed_sha256`. Add validation in `__post_init__` preventing `human_reviewed=True` without matching record fields.
  - `class QcRecord`: Define dataclass with JSON serialization/deserialization and validation.
- `src/hawedit/pipeline.py`:
  - Remove `--qc-pass` from `build_parser()`.
  - Add `--qc-record` argument.
  - Parse `QcRecord` and construct `Qc`.
- `src/hawedit/delivery.py`:
  - Add Clause 8 (or QC record clause) in `reconcile_delivery` verifying `clip.qc.reviewed_sha256 == measurement.file.sha256`.
- `src/hawedit/proposals.py`:
  - In `commit_boundary_revision` and `commit_caption_revision`: bind the interactive approver's name (`approver`), ISO timestamp, and rendered MP4 SHA-256 to `Qc`.
- `src/hawedit/policy.py`:
  - Assert that `review_record` / `qc_record` are forbidden capabilities for agent tool registration.
