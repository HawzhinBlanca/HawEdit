# Main delivery-audit adaptation — 2026-08-10

## Finding

Protected-main commit `5eba372931eb6aa97edfca70cce6fbcc0718d8e3` corrected an audit
statement against its flat-file delivery guard and added a derived decision-citation check.
Readiness had already replaced that guard with `ArtifactBundle`: a unique hidden directory owns
an attempt, and the exact five-file set is published by one no-replace directory rename.

Copying main's sentence would therefore have introduced a new false claim. In this tree, a hidden
private attempt does not block `_assert_no_existing_artifacts`; a visible final bundle directory
does. Legacy flat artifacts are also refused and never treated as resumable current-format output.

## Adaptation

- `test_the_audit_describes_the_atomic_delivery_behaviour_this_tree_has` executes both current
  guard outcomes and binds the `AUDIT_REPORT.md` debt statement to them.
- `test_every_decision_the_root_documents_cite_exists` derives all root Markdown documents except
  the register and requires every `D-NNN` citation to resolve.
- Main's historical D-154 was not copied because readiness already assigns D-154 to a different
  decision. This adaptation is D-237.

## Acceptance

The focused claims/pipeline suite and the canonical gate must pass before the ancestry join. The
later merge record will additionally prove that the merge tree equals its verified first parent;
tree equality is not a replacement for running the gate.
