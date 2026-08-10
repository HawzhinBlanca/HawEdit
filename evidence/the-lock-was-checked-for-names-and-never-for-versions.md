# The gate's dependency lock was checked for names, never for versions

D-139 gave the gate a hashed lock and three guards: every distribution pinned *and* hashed, CI
installing it under `--require-hashes`, and every `pyproject.toml` dependency present in the lock.
The third compares **names**. Nothing compared the versions.

## Why that matters more here than in most repositories

CI does not install `pyproject.toml`. It installs the lock and then the project with `--no-deps`:

```yaml
.venv/bin/pip install --require-hashes \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  -r requirements/gate-linux-py311.txt
.venv/bin/pip install -e . --no-deps
```

`--no-deps` means the runner never resolves `pyproject.toml` at all. Whatever the lock says **is**
the program the gate of record runs on. A pin bumped in `pyproject.toml` and not recompiled into
the lock does not fail, conflict, or warn — the two files simply disagree, and the file every
reader consults is the one that loses.

## Measured

`pyproject.toml` declares 11 exact pins for the gate's closure. Against the committed lock:

```
OK fonttools                    declared 4.55.3           lock 4.55.3
OK klpt                         declared 0.1.7            lock 0.1.7
OK mypy                         declared 1.15.0           lock 1.15.0
OK numpy                        declared 2.2.1            lock 2.2.1
OK onnxruntime                  declared 1.20.1           lock 1.20.1
OK opencv-python-headless       declared 4.12.0.88        lock 4.12.0.88
OK pytest                       declared 8.3.4            lock 8.3.4
OK ruff                         declared 0.9.6            lock 0.9.6
OK scenedetect                  declared 0.6.5            lock 0.6.5
OK silero-vad                   declared 5.1.2            lock 5.1.2
!! torch                        declared 2.13.0           lock 2.13.0+cpu
```

No drift today, and `torch` is not drift either — see the rule below. So this is a missing guard,
not a live defect: **never computed**, rather than computed and discarded.

The hole itself reproduces exactly. Bumping `ruff==0.9.6` to `0.12.0` in `pyproject.toml`, lock
untouched:

```
baseline green: True

pyproject says ruff==0.12.0, the lock still says 0.9.6
suite still green: True

restored and green: True
```

All 1510 tests green, and CI would have gone on linting with 0.9.6 — the gate's own linter, a
version nobody declared.

## The rule, and why it is not just string equality

`torch==2.13.0` is satisfied by the lock's `2.13.0+cpu`. That is PEP 440: an `==` specifier
carrying no local segment ignores the candidate's. It is also deliberate here — §6 puts Stage 0 on
CPU, and `scripts/lock-gate-deps.sh` resolves against `download.pytorch.org/whl/cpu` because the
CUDA build is ~2 GB of runner disk for kernels the gate never calls.

`_lock_satisfies` accepts exactly that one difference:

| declared | lock | satisfied | why |
|---|---|---|---|
| `2.13.0` | `2.13.0+cpu` | yes | PEP 440 local segment, the CPU wheel |
| `0.9.6` | `0.9.6` | yes | equal |
| `2.13.0` | `2.9.0+cpu` | no | a real bump wearing a local tag |
| `2.13.0` | `2.13.1` | no | different upstream version |
| `2.13.0` | `2.13.0.post1` | no | a post-release is not a local segment |
| `2.13.0` | absent | no | nothing to satisfy it |
| `2.13.0+cpu` | `2.13.0` | no | a declared local segment names a build, so it is exact |

The control's last assertion is that the lock still carries `+cpu` at all. Without it the first
row of that table would keep passing while describing nothing this repository does — a rule
exercised only by its own unit test is a rule that can quietly stop applying.

## The third guard: ranges

A `>=` spec in `dev` or `media` would make the version comparison skip that distribution in
silence, which is the same failure one level up. `test_every_gate_dependency_is_an_exact_pin_so_the_lock_can_be_compared_to_it`
requires them all to stay exact, so a future range fails loudly and forces the decision. The
`gpu`, `cloud` and `asr` extras keep their ranges — they are not what the gate installs, and
pinning a CUDA stack for Linux from this Windows host would be a guess.

## Mutation audit — 7/7

```
baseline green: True
CAUGHT    the defect: a declared pin drifts and the lock is not recompiled
           red: test_the_lock_carries_the_versions_pyproject_declares
CAUGHT    the same drift from the other side: the lock moves and pyproject does not
           red: test_the_lock_carries_the_versions_pyproject_declares
CAUGHT    a gate dependency becomes a range, so the version comparison skips it
           red: test_every_gate_dependency_is_an_exact_pin_so_the_lock_can_be_compared_to_it
CAUGHT    the rule ignores a local segment on the declared side too
           red: test_the_local_version_rule_accepts_the_cpu_wheel_and_nothing_looser
CAUGHT    the rule compares only major.minor
           red: test_the_local_version_rule_accepts_the_cpu_wheel_and_nothing_looser
CAUGHT    the rule treats absent-from-the-lock as satisfied
           red: test_the_local_version_rule_accepts_the_cpu_wheel_and_nothing_looser
CAUGHT    the lock loses the CPU wheel, so the local-version rule is exercised by nothing real
           red: test_the_local_version_rule_accepts_the_cpu_wheel_and_nothing_looser
7/7
restored and green: True
```

Each was caught by the guard written for it, and each mutation is a state the repository could
actually reach: two are the drift itself from either side, one is the range that would make the
comparison skip silently, three attack the local-version rule, and the last removes the only real
thing that rule describes. Every mutation was lint-clean, so none of these results is `ruff`
reporting on itself (D-148, D-150).
