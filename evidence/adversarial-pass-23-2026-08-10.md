# Adversarial pass 23 - identity-bound atomic delivery publication

Date: 2026-08-10
Baseline: `3c7463f2cfb43f1aea9d9d2179c83dc05bdd647e`

## Finding

The five-file delivery set was staged privately, but its directory boundary and final rename were
not equally strong. `ArtifactBundle.create` called `root.resolve()`, so a planted directory symlink
or Windows junction redirected every rendered and editorial artifact outside the declared work
root. The bundle then used a check followed by `os.rename`. On POSIX, that rename may replace an
empty destination directory created by another worker after the check, contradicting the
write-once winner contract.

Private artifact validation also checked a pathname before reopening it for `fsync`, leaving a
replacement gap and accepting hardlinked files.

## Fix

- The delivery root is now lexical-absolute, lstat-validated as a real non-reparse directory, and
  bound by device/inode identity for the lifetime of the bundle.
- The unpredictable private staging directory is bound independently and revalidated before and
  after staging, validation, publication, and cleanup operations.
- Each artifact must be one nonempty, single-link regular file. Its lstat identity is matched to a
  no-follow descriptor before and after `fsync`.
- Publication uses one shared native no-replace primitive: Windows `MoveFile`, Linux
  `renameat2(RENAME_NOREPLACE)`, or Darwin `renamex_np(RENAME_EXCL)`. Unsupported POSIX platforms
  fail closed instead of falling back to check-then-rename.
- After publication, the final directory and all five artifact identities are revalidated before
  the pipeline is allowed to report delivery success.
- Checkpoint publication now delegates to the same primitive, preserving its existing error
  contract and eliminating two implementations of this security property.

## Discriminating controls

Zero-skip regressions prove that a simulated Windows reparse root is rejected, real root and
staging rename/recreate attacks are detected, a planted hardlink cannot touch its external
victim, and a file swapped between lstat and descriptor open is refused. The native race test
creates an empty destination, records its inode, and proves publication preserves both that inode
and the private source. A second test forces the POSIX branch and asserts the kernel call carries
`RENAME_NOREPLACE` rather than an ordinary rename.

Focused verification from checkout source:

```text
240 passed
Ruff: all checks passed
Ruff format: clean
mypy: success, no issues in 3 source files
```
