# The guard's path boundary is inert on Windows

> Measured 2026-08-13 on HawaPC01 against `3b83897`, by feeding
> `scripts/guard-pretooluse.sh` the same payload shape `scripts/guard-test.sh:40` uses:
> `{"tool_name":"Edit","tool_input":{"file_path":"…"}}`. Exit 2 = blocked, exit 0 = allowed.

`scripts/guard-pretooluse.sh:96-111` and `:113-129` decide protection with shell `case` globs
written with `/` separators — `*/.gate/*|.gate/*`, `*/secrets/*|secrets/*`, and the enforcement
list including `scripts/verify.sh` and `scripts/test-count.floor`. The guard compares the
`file_path` string; the operating system resolves it as a path. On Windows those two disagree.

```
=== baseline: the spellings guard-test.sh already covers ===
  BLOCKED (correct)  .gate/last-test-run.xml
  BLOCKED (correct)  /home/me/HawEdit/.gate/last-test-run.xml
  BLOCKED (correct)  scripts/verify.sh
  BLOCKED (correct)  scripts/test-count.floor

=== native Windows separators ===
  ALLOWED (BYPASS)   C:\Users\Wareen\Desktop\HawEdit\.gate\last-test-run.xml
  ALLOWED (BYPASS)   .gate\last-test-run.xml
  ALLOWED (BYPASS)   scripts\verify.sh
  ALLOWED (BYPASS)   scripts\test-count.floor
  ALLOWED (BYPASS)   secrets\key.json
  ALLOWED (BYPASS)   .venv\Lib\site-packages\x.py

=== case variation (the filesystem is case-insensitive; the glob is not) ===
  ALLOWED (BYPASS)   .Gate/last-test-run.xml
  ALLOWED (BYPASS)   Scripts/verify.sh

=== redundant separators (platform-independent) ===
  BLOCKED (correct)  .gate//last-test-run.xml
  ALLOWED (BYPASS)   scripts//verify.sh
  ALLOWED (BYPASS)   scripts/./verify.sh
  BLOCKED (correct)  scripts/../scripts/verify.sh
```

## Why this went unnoticed

Two reasons, and both are the kind that keep a hole open for a long time.

**The guard is half-live.** The *command* side works: it blocked `rm -rf` and a `cp` naming an
enforcement file during this session's ordinary work, which reads as a guard doing its job. Only
the `file_path` side — the one that governs Edit and Write — is inert.

**Its own test suite cannot express the failing case.** `scripts/guard-test.sh:40` builds payloads
with `printf '…"file_path":"%s"…'`, and all 56 checks use POSIX spellings. The 56 passing checks
are true and prove nothing about the platform the repository is developed on.

The practical consequence, measured rather than supposed: every `file_path` sent by the agent in
this session has been a native `C:\Users\Wareen\Desktop\HawEdit\…` path. For the duration of that
work the `.codystem-allow-self-edit` requirement was not enforced — an enforcement file could have
been edited by an Edit call with no sentinel, no refusal, and no line in `git status` to show it.
AGENTS.md's claim that the sentinel "makes the self-edit deliberate and visible" holds only for
paths spelled the way the guard expects.

`.gate/` is the sharpest case. AGENTS.md calls it "where the gate writes the test report it then
grades itself against — hand-writing it is forging the evidence D-093 exists to produce", and it
is the one directory the guard documents as having no sentinel escape. `.gate\last-test-run.xml`
reaches it.

## Scope

`scripts//verify.sh` and `scripts/./verify.sh` bypass on every platform, so the Linux CI runner is
not exempt from that pair. The Windows and case variants matter on this machine and any other
Windows checkout.

This changes nothing about CI's verdict: `.github/workflows/gate.yml` re-runs the gate from
committed source, and a guard bypass leaves its evidence in the diff. What it changes is the
local claim that a self-edit is always visible.

## Not measured

Whether Claude Code normalises `file_path` before the hook sees it on other platforms or other
versions — this is one client on one machine. Whether the `%s`-into-JSON payload construction in
`guard-test.sh` can represent a backslash path at all without escaping (a separate question from
whether the guard would then block it). No fix is proposed here; this file records the
measurement only.
