# ASR Segment Checkpoint Research

Baseline: 422a3be82b659c09f1d653c59458ee12aafa058b, 2026-10-06.
Approved parent scope: evidence-based-studio Phase 2, existing artifact recovery;
owner: "PLEASE IMPLEMENT THIS PLAN", "approve all and fix them", "ok just fix it".

The fresh ZAR38 producer times out at 19020 seconds during Qwen validation;
controller 19201.437921 seconds. No worker output, raw transcript or video exists.
Canonical inference returned before validation, as evidenced by read-only stacks,
not a saved complete result. The worker only persists after both whole passes.
See external asr-context-producer-20261006/full-source-retest/terminal.json and
stderr SHA256 3cdbd34dad426e54725049f869e3de4d9af31ccebaa72702c608d628aaf01592.
Hardware/library provenance is in that record and the linked vault incident.

Actual Serena LSP definitions/references (10 pairs, source unchanged):
asr-segment-checkpoint-map-422-20261006/serena-map.json. No invented signatures.
Existing stage checkpoints do not persist individual ASR/validator operations.
Reuse existing PrivateDirectory/write_text_atomic for fsynced owner-private
records. DrvFS reports mode 777 even for host-private directories: use native
Linux owner-private checkpoint storage, not a permission-check bypass.
Before cache admission, reuse the existing canonical card integrity/empty-override
guards; temporary guard directory names are not cache identities. Verify all
canonical asset bytes and validator files before reading reused operations.
This does not close the adapted loader's separate held-descriptor gap.

Retain BLUEPRINT sections 2/3/4.2/8.1, D-278 hard stop, D-281 natural EOS,
D-283 whole-VAD grouping. No model, decoder, stopping, timeout or confidence-router
change. No paid routes. Blocker #24 still requires qualified current VEX review.
