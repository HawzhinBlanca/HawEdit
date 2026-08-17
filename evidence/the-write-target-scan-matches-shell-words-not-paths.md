# The write-target scan matches shell words, not paths

> Measured 2026-08-13 on HawaPC01 against `db53dfa`, by feeding
> `scripts/guard-pretooluse.sh` Bash payloads of the shape `guard-test.sh:41` uses.
> Exit 2 = blocked, exit 0 = allowed. Companion to
> `the-guards-path-boundary-is-inert-on-windows.md`, which is the same root cause on the
> other half of the guard.

The write-target scan exists because, as its own comment says, "the file_path boundary above is
one shell redirect wide". It extracts redirect targets with

```sh
grep -oE '[0-9]*&?>>?\|?[[:space:]]*[^[:space:]<>|&;()]+'
```

and compares each against the protected-path globs. The character class excludes whitespace and
shell metacharacters — but not quotes. So the candidate it tests is the raw shell *word*, before
the shell performs quote removal, variable expansion or working-directory resolution.

## Measured

```
=== baseline: the spellings guard-test.sh covers ===
  BLOCKED  echo x > .gate/last-test-run.xml
  BLOCKED  echo x > scripts/test-count.floor
  BLOCKED  cp /tmp/x scripts/verify.sh
  BLOCKED  printf 9 >> scripts/test-count.floor

=== ordinary quoting ===
  ALLOWED  echo x > '.gate/last-test-run.xml'
  ALLOWED  echo x > ".gate/last-test-run.xml"
  ALLOWED  echo x > "scripts/test-count.floor"

=== another tool for the same write ===
  ALLOWED  sed -i s/1/2/ scripts/test-count.floor

=== indirection ===
  ALLOWED  f=.gate/last-test-run.xml; echo x > $f
  ALLOWED  cd .gate && echo x > last-test-run.xml

=== control ===
  ALLOWED  ls -la
  ALLOWED  bash scripts/verify.sh
  ALLOWED  cat .gate/last-test-run.xml
```

Four distinct mechanisms, one cause:

- **Quotes are captured as part of the path.** `'.gate/last-test-run.xml'` does not match the glob
  `.gate/*` because of the leading quote. This is the one that matters: it is not evasion, it is
  how shell is ordinarily written.
- **Variables are not expanded.** The candidate is the literal `$f`.
- **The working directory is not resolved.** After `cd .gate`, the target word is
  `last-test-run.xml`, which matches no protected glob.
- **`sed -i` emits no candidate at all.** The writing-command list is `(cp|mv|install|ln|tee)`;
  `sed -i`, `truncate`, `dd` without `of=`, and an editor are not in it. Only `dd of=` is special-cased.

## Why this compounds rather than repeats

`.gate/` is the directory AGENTS.md singles out as having no sentinel escape — "hand-writing it is
forging the evidence D-093 exists to produce". On Windows, both halves of the guard now fail for
that one directory: the `file_path` side accepts `.gate\last-test-run.xml` (companion record), and
the command side accepts `echo x > '.gate/last-test-run.xml'`. The guard's own bash test suite
passes 56 checks because every one of them uses an unquoted POSIX path.

Read together with `the-gate-cannot-tell-its-own-report-from-another-runs.md`, the three findings
share a shape: a check that compares a *rendering* of a thing against a rule, while something else
resolves that thing — a path, a shell word, a file's provenance.

## What this is not

Not a remote attack, and not something CI inherits: `.github/workflows/gate.yml` re-runs the gate
from committed source, and a write to `.gate/` on a developer's machine leaves no trace there. It
is a local integrity boundary that reads as stronger than it is. An agent that has been told the
sentinel makes self-edits visible in `git status` — as AGENTS.md says, and as I believed for this
entire session — is relying on a boundary that ordinary quoting steps over.

## Not measured

Whether the redirect regex can be defeated by a target containing a metacharacter it does exclude;
whether `should_block` is reached at all for tab-separated redirects; whether the double-quoted
result above survives the JSON encoding faithfully — the single-quoted case is the unambiguous one
and is the one this record rests on. No fix is proposed. Normalising the candidate before matching
— strip surrounding quotes, refuse to decide on a word containing `$`, resolve against the
command's working directory — is the obvious shape, and it edits an enforcement file.
