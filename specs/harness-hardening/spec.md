# harness-hardening — acceptance criteria (EARS)

Five reproduced holes in what the harness guarantees. Each criterion names the record that
measured it.

## H4 — CI's anti-skip steps (the only one CI does not wash out)

- **AC1** WHEN a step's pytest invocation exits non-zero for any reason, THE anti-skip step
  SHALL fail, rather than proceeding to its `grep`.
- **AC2** WHEN the named tests do not exist or are all deselected, THE anti-skip step SHALL fail
  even though the word "skipped" does not appear in the output.
- **AC3** THE workflow SHALL NOT contain a step that pipes pytest through `tee` without
  `set -o pipefail`.

## H1 — an augmented pytest

- **AC4** WHEN `PYTEST_ADDOPTS` is set in the environment, THE gate SHALL refuse to run, naming
  it, in the same manner as an overridden step.
- **AC5** THE refusal SHALL NOT be a second copy of `verify.sh`'s override rule living in the
  guard — one place decides (`verify.sh:157-161`).
- **AC6** WHEN the gate refuses for this reason, THE exit code SHALL be the one already meaning
  "the gate's steps were overridden", so `claude-stop-verify.sh`'s map needs no change.

`PYTHONPATH` is deliberately **not** covered by a criterion here — see plan.md; refusing it
outright may break legitimate local setups, and that is a decision for a human, not an omission.

## H5 — a report with no provenance

- **AC7** WHEN the gate deletes the test report before running pytest, THE gate SHALL record a
  token identifying this run.
- **AC8** WHEN the gate grades a report, THE gate SHALL refuse a report that does not carry this
  run's token, even if that report is newer than the run started.
- **AC9** THE existing freshness refusal SHALL keep working — a report older than the run start
  is still refused (`gate.py:194`, control-tested).

## H2 / H3 — the guard compares renderings, not paths

- **AC10** WHEN a `file_path` names a protected path using native Windows separators, THE guard
  SHALL block it.
- **AC11** WHEN a `file_path` names a protected path whose directory component differs only in
  case, THE guard SHALL block it.
- **AC12** WHEN a shell command redirects into a protected path with the target quoted, THE guard
  SHALL block it.
- **AC13** WHEN a shell command's write target is a bare variable reference, THE guard SHALL
  block it, because it cannot know what the variable holds.
- **AC14** THE 56 checks in `scripts/guard-test.sh` SHALL all still pass — a normalisation that
  over-blocks makes the harness unusable, and that suite is the regression evidence.

## Out of scope, stated so it is a decision and not a gap

- `sed -i`, `truncate`, an editor, and every other writing verb outside `(cp|mv|install|ln|tee)`.
  Enumerating verbs is a losing game; the redirect and the `file_path` boundary are the two that
  carry the guarantee. Recorded in `evidence/the-write-target-scan-matches-shell-words-not-paths.md`.
- A `cd` earlier in the same command changing what a relative target resolves to. Same reason.
- The two `update-ledger.sh` exactness holes, which have their own approved-pending spec at
  `specs/ledger-id-exactness/`.
