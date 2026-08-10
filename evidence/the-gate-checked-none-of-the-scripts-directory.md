# The gate ran the right programs over only part of the repository

`tests/test_gate.py` already asked *which programs* the gate runs, and refuses one whose
provenance is unchecked (D-093). Nothing asked **what they read**.

Measured before this change:

```
LINT_CMD="${LINT_CMD-$PY -m ruff check src tests}"
FORMAT_CMD="${FORMAT_CMD-$PY -m ruff format --check src tests}"
files = ["src", "tests"]          # [tool.mypy]
```

`scripts/` appears in none of them, so every Python file in that directory was linted by
nothing and typechecked by nothing — while `README.md` describes the step as
*"lint + typecheck + format + tests — this decides DONE"* without qualification. That is where
D-160's defect sat unnoticed for four days.

## What the widening costs: nothing

```
=== as committed (the fix in place) ===
clean tree
    ruff  rc=0  All checks passed!
    mypy  rc=0  Success: no issues found in 99 source files
```

Both tools pass on `src tests scripts` today, and mypy's file count goes 98 → 99. There is
exactly one Python file under `scripts/` (`measure_collisions.py`); the other seven entries are
shell and PowerShell.

## What the widening does *not* buy, measured rather than assumed

The tempting claim is that this would have caught D-160. It would not. Both of that iteration's
defects, written the way an author who meant them would leave the file:

```
D-160 defect 1, written cleanly (POSIX path, import removed)
    ruff rc=0 rules=-
    mypy rc=0 rules=-
D-160 defect 2, written cleanly (no pinning, import removed)
    ruff rc=0 rules=-
    mypy rc=0 rules=-
```

A wrong path string is not a lint error and not a type error. A first pass reported `rc=1` for
both, but each of those edits had left an orphaned import behind — `F401` fired on the *edit
shape*, not on the defect. What actually protects that class is D-160's subprocess test, which
runs the script and requires exit 0.

What the widening does reach, on the same file:

| injected | ruff | mypy |
|---|---|---|
| undefined name (`UNDEFINED_ROOT`) | rc=1 (`F821`) | rc=1 |
| wrong return annotation | rc=0 | rc=1 |
| unused import | rc=1 (`F401`) | rc=0 |

Worth having — the undefined-name row is the shape of my own bad mutation last iteration — and
worth stating precisely rather than overclaiming.

## `models/` is not repository content

The first run of the new scope test failed, naming eleven files:

```
models/MCG-NJU__VideoChat3-4B/modeling_videochat3.py
models/MCG-NJU__VideoChat3-4B/processing_videochat3.py
models/Qwen3-VL-Embedding-2B/scripts/qwen3_vl_embedding.py
models/Qwen3-VL-Reranker-2B/scripts/qwen3_vl_reranker.py          … and 7 more
```

These are **downloaded checkpoint code**, not ours. `.gitignore:27` matches `models/*`, and the
only tracked files under it are `revisions.json` and `sources.json`:

```
tracked under models/ : models/revisions.json, models/sources.json   (2)
tracked *.py under models/ : 0
git check-ignore -v : .gitignore:27:models/*
total tracked *.py : 99
```

So the enumeration asks **git**, not the filesystem. A directory walk answers a different
question, and excluding `models/` by name would need a blocklist that goes stale the next time a
checkpoint lands. `.gitignore` already draws that line and is the authority on it — and the 99
tracked Python files are exactly the 99 mypy now reports.

## The two guards

`test_the_gates_three_python_steps_read_the_same_paths` requires lint, format and typecheck to
name the same roots — mypy's list lives in `pyproject.toml` and the other two in `verify.sh`, so
nothing else keeps them equal, and a file linted but not typechecked is checked less than it
looks. Its controls: the scope must be non-empty (set equality is satisfied by three empty sets)
and every named root must be a real directory.

`test_the_gate_reads_every_python_file_in_the_repository` derives the requirement from the
repository rather than from a list, so the next top-level package fails here until both files
name it. Its control asserts the enumeration found more than 50 files, because `git ls-files`
returns empty rather than failing when it cannot answer — and an empty enumeration would satisfy
the real assertion vacuously.

## Mutation audit — 7/7, after 6/7

```
baseline green: True
CAUGHT    the regression: the lint step narrows back to `src tests`
           red (2): test_the_gate_reads_every_python_file_in_the_repository,
                    test_the_gates_three_python_steps_read_the_same_paths
CAUGHT    the regression: the format step narrows back to `src tests`
           red (1): test_the_gates_three_python_steps_read_the_same_paths
CAUGHT    the regression: mypy narrows back to `src tests`
           red (1): test_the_gates_three_python_steps_read_the_same_paths
CAUGHT    a tracked Python file arrives outside every root
           red (1): test_the_gate_reads_every_python_file_in_the_repository
CAUGHT    the enumeration stops asking git and returns nothing
           red (1): test_the_gate_reads_every_python_file_in_the_repository
CAUGHT    the scope may name a directory that does not exist
           red (5): … plus four gate-as-subprocess tests, because a non-existent path makes
                    ruff itself exit non-zero
SURVIVED  the same-paths check accepts an empty scope
6/7
```

Mutation 4 is worth naming: it creates `tools_for_this_audit/helper.py` and `git add -N`s it, so
the repository genuinely contains a tracked Python file outside every root. That is the state the
widening exists for, reached rather than simulated.

**The survivor was mine, and of the kind I keep repeating.** Neutering the empty-scope control
while no scope is empty measures nothing — a guard against empty scopes has nothing to see. Paired
with the state it describes (all three steps naming whitespace, so set equality is satisfied by
three empty sets):

```
all three steps name nothing, control INTACT   -> green=False red=[reads_every_python,
                                                                  three_python_steps]
all three steps name nothing, control REMOVED  -> green=False red=[reads_every_python]
```

`test_the_gates_three_python_steps_read_the_same_paths` goes **green** without the control: three
empty lists agree with each other perfectly. Its sibling still reddens — 99 tracked files fall
outside an empty root list — which is defence in depth working, not a reason to drop the control.
**7/7 with the pair measured.**

One detail cost a run: whitespace, not emptiness, is the shape that reaches the control. With a
single space the pattern's own trailing space consumes it, `([^}]+)` matches nothing, and
`_gate_scope` fails earlier with a different message. Two spaces reach `assert lint`. A control
can be unreachable by the shape you happen to try and load-bearing for the one you did not.
