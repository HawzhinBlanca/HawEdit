# Adversarial pass 22 — transcript store root binding

Date: 2026-08-10
Baseline: `0b8f7d6ebd92b3b28203f1aaeb5f1da4444c6395`

## Finding

The transcript filenames and publication lock were hardened, but their parent directory was not.
`TranscriptStore(root)` ran `root.mkdir(parents=True, exist_ok=True)` and retained the pathname.
That call follows a pre-existing directory symlink or Windows junction. All subsequent raw,
digest, lock, and normalized artifacts then land at the link target outside the declared store.
Replacing the directory after construction produced the same redirection with no identity check.

This bypass sits above the individual-file defenses: a safe `media_id`, no-follow lock open, and
atomic final replacement all operate inside the wrong directory once the root is redirected.

## Fix

The store now:

- converts its root to a lexical absolute path without resolving symlinks;
- creates the directory if absent, then uses `lstat` to require a real directory with no Windows
  reparse attribute;
- records the directory's device and inode;
- revalidates type, reparse state, and identity before and after each publication lock;
- revalidates around reads that do not otherwise hold that lock.

## Discriminating controls

The zero-skip tests simulate both POSIX and Windows path mechanisms independent of the host. A
third test constructs a real store, renames its root aside, creates a replacement directory at the
same pathname, and calls `write_raw`. The call refuses `root changed identity`; neither the old nor
replacement directory contains a lock, raw transcript, or digest.

Focused verification from checkout source:

```text
213 passed
Ruff: all checks passed
Ruff format: 2 files already formatted
mypy: success, no issues in 1 source file
```
