# Tasks — Human Review Record (`specs/qc-record`)

- [x] T1 Define `QcRecord` and extend `Qc` dataclass with `reviewed_by`, `reviewed_at`, and `reviewed_sha256` invariants in `src/hawedit/clip.py`
- [x] T2 Add Policy Gate check in `src/hawedit/policy.py` preventing agent tool registration of review record writers
- [x] T3 Add Clause 8 to `reconcile_delivery` in `src/hawedit/delivery.py` enforcing `clip.qc.reviewed_sha256 == measurement.file.sha256`
- [x] T4 Replace `--qc-pass` CLI flag with `--qc-record <path_or_json>` in `src/hawedit/pipeline.py`
- [x] T5 Bind human approver, ISO timestamp, and rendered MP4 SHA-256 to `Qc` in `src/hawedit/proposals.py`
