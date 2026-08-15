# Bounded Path B refusal diagnostics — 2026-08-15

This is report-integrity and live source-policy evidence. It is not a visual-quality measurement.

## Reproduced failure

At protected-main source, constructing `UnreadableScene` with
`"private\\x00\\n" + "X" * 1_000_000` produced a 1,000,009-character reason containing both a
NUL and newline. `VideoChat3Reader.read_scenes` constructs that record directly from caught
`PathBError` text, and `VisualDiscoveryResult.to_dict` emits it into the run report without passing
through the pipeline's bounded `StageSkipped` formatter.

## Enforced boundary

`UnreadableScene` now requires a real, non-empty string; converts non-printable characters and
arbitrary whitespace to one printable line; preserves ordinary short one-line messages exactly;
and caps the serialized value at 1,024 characters with a deterministic ellipsis. The invariant is
on the record rather than one adapter, so injected `VideoUnderstanding` producers cannot bypass it.

Named proofs:

- `test_unreadable_reason_is_a_bounded_printable_line_without_losing_short_detail`
- `test_unreadable_reason_refuses_a_non_string_runtime_value`
- `test_read_scenes_bounds_and_single_lines_a_path_b_exception`

The first drives a one-million-character/control-bearing reason and proves the discarded
API-key-shaped tail is absent. The reader regression preserves two readable siblings while the one
refused survivor keeps its exception type and bounded useful prefix.

## Verification before the canonical gate

- Path B plus the real reader: 74 passed.
- Path B, reader, visual composer and pipeline adjacency: 316 passed.
- VEX/policy, Path B, reader and visual composer: 147 passed.
- Ruff check and formatting: clean.
- Strict mypy over the three changed/affected Python files: clean.

## Exact source-bound runtime

The reviewed HawEdit package digest is
`87a1ca6200a356368e9f7f722eea88a0b381b0f1a471740ec5f10e495b5a3510`. Only the VEX
applicability source identity changed; no vulnerability disposition was altered.

`hawedit-asr-setup --distribution Ubuntu` completed in 177.3 seconds, imported OmniASR and saw
both CUDA GPUs. The live VEX gate completed in 146.4 seconds and accepted all 12 findings against
all 12 current reviewed dispositions. Its write-once 10,382-byte local artifact has SHA-256
`c6632369f31ea5b1b7bb0fc69a7ea0399a023529ae0b213dc16db6337871c52f`.

The host-local JSON remains outside the repository. A protected-main hosted artifact and the
canonical full gate are still required before promotion.
