# Seven shell scripts, including the gate itself, read by no linter

D-161 widened `verify.sh` to `ruff check src tests scripts`. Ruff reads Python. The seven shell
scripts sitting in that same directory — **the gate's own script**, and the fetchers that
download, checksum, unzip, `chmod +x` and execute a 140 MB binary — were read by nothing, and
D-161 named that as remaining debt.

```
scripts/build-wheel.sh      scripts/lock-gate-deps.sh   scripts/verify.sh
scripts/fetch-ffmpeg.sh     scripts/setup.sh
scripts/fetch-models.sh     scripts/verify-sha256.sh
```

All seven are tracked, and all seven live under `scripts/`, so one glob covers them.

## What shellcheck finds today: nothing

```
shellcheck --severity=style --format=gcc scripts/*.sh
exit=0
total findings: 0
```

**With a control**, because a clean result and a result that read no files look identical:

```
$ printf 'ls $file\ncat foo | grep bar\nif [ $x == 1 ]; then echo hi; fi\n' > bad.sh
$ shellcheck --severity=style --format=gcc bad.sh
bad.sh:1:1: error: Tips depend on target shell and yours is unknown … [SC2148]
bad.sh:1:4: warning: file is referenced but not assigned … [SC2154]
bad.sh:1:4: note: Double quote to prevent globbing and word splitting. [SC2086]
bad.sh:3:6: warning: x is referenced but not assigned. [SC2154]
```

The tool works and the scripts are clean. **So this is a ratchet, not a repair** — stated plainly
because a guard added for zero findings is worth exactly its future, and claiming otherwise would
be the kind of overclaim D-161 was careful to avoid.

## The optional checks, and why they are not enabled

`--enable=all` reports 131, which sounds alarming and is not:

| rule | count | what it is |
|---|---|---|
| SC2250 | 122 | prefer `${var}` over `$var` even when unnecessary — pure style |
| SC2310 | 6 | a function invoked in a condition, so `set -e` is disabled inside it |
| SC2312 | 3 | a command in a substitution whose return value is masked |

SC2312 is the shape of D-144's real defect (`| tail` reported `tail`'s status), so all three were
read. All three are `$(...)` inside `[[ ]]` tests where the comparison already handles failure —
e.g. `[[ "$(uname -s)" != Linux* ]]`, which refuses when `uname` fails.

SC2310's six are `verify_rtl` invoked as `if verify_rtl …` and `if ! verify_rtl …`. That one
decides whether an ffmpeg can shape Arabic script — §4.3's failure is *"invisible until a client
sees the burned-in captions"* — so it was read line by line:

```bash
verify_rtl() {
  local binary="$1" buildconf missing=()
  buildconf="$("$binary" -hide_banner -buildconf 2>&1)" || return 1
  for lib in libass libharfbuzz libfribidi; do
    grep -q -- "--enable-${lib}" <<<"$buildconf" || missing+=("$lib")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then … return 1; fi
}
```

Every failure path is explicit — `|| return 1`, `|| missing+=(…)` — so the function never relied
on `set -e` and disabling it changes nothing. **Default severity, not `--enable=all`:** turning on
122 brace-style notes to reach three benign ones would make the step noise, and a noisy check is
one people learn to ignore.

## Why CI and not `verify.sh`

`shellcheck-py` on PyPI ships **a binary and no importable module**:

```
shellcheck_py-0.11.0.1.dist-info/
bin/shellcheck.exe
```

`verify.sh` runs its steps as `$PY -m <tool>`, and `assert_tools_are_from_this_environment`
(D-093) vouches for each by importing it — `GATE_TOOLS = ("pytest", "ruff", "mypy")`. A binary
cannot be checked that way, so adding it as a gate step would put a program into the gate that its
own provenance rule cannot see. `tests/test_gate.py` already says why that is unacceptable: *"a
tool the gate runs but does not check is a hole the shape of the one just closed."*

ubuntu-latest carries shellcheck, and CI **is** the gate of record, so the step goes there. The
honest limitation: `bash scripts/verify.sh` on a developer machine does not run it. Recorded
rather than papered over.

`shellcheck --version` runs first so an absent tool fails the step instead of linting nothing.

## Mutation audit — 6/6, after 5/6 and two corrections of mine

```
baseline green: True
CAUGHT    the step stops linting the scripts
CAUGHT    the step lints one script instead of the glob
CAUGHT    the presence proof is dropped, so a missing tool could lint nothing
CAUGHT    a tracked shell script arrives outside the glob
CAUGHT    the enumeration stops asking git and returns nothing   [LINT DIRTY]
SURVIVED  the scope control accepts an empty listing
5/6
```

Every catch names `test_ci_lints_every_shell_script_this_repository_tracks`. Mutation 4 writes
`tools_for_this_audit/helper.sh` and `git add -N`s it, so the repository genuinely contains a
tracked shell script the glob cannot reach — the state reached, not simulated.

**Two of those six results were not trustworthy, and both faults were mine.**

*Mutation 5 was lint-dirty.* Replacing the `git ls-files` argv left the helper's `pattern`
parameter unused, so ruff reddened the four gate-as-subprocess tests and the CAUGHT partly
measured ruff. Redone by changing the **call site** instead — the helper stays intact and used:

```
5  enumeration returns nothing, control INTACT   -> green=False lint_clean=True
                                                    red=[test_ci_lints_every_shell_script…]
```

*Mutation 6 measured nothing.* Neutering the empty-listing control while the listing is full is a
guard with nothing to see — the same isolated-mutation trap as D-161, D-157, D-156, D-155 and
D-149. Paired with the state it exists for:

```
6  enumeration returns nothing, control REMOVED  -> green=True  lint_clean=True  red=[]
```

**Green.** Without that control an empty listing satisfies the real assertion vacuously: no
tracked scripts means none outside the glob, and the test passes while checking nothing. With it,
red. The control is load-bearing, and **6/6** once both mutations are honest.
