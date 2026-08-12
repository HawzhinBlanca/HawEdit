# Adversarial pass 31 — the gate itself

**Target: M0.1, DONE.** *"gate refuses a no-op command instead of printing green."*

Everything else in this repository rests on it. Every DONE row, every `N/N mutations`, every "CI
green" in this session is an assertion the gate made; if the gate can be fooled, all of it is worth
less than it reads. It has been fooled twice already — D-092 (`PY=true.exe`: VERIFY OK in 1 s,
exit 0, no report written) and D-093 (a forged `pytest/__main__.py` on PYTHONPATH: VERIFY OK in 4 s
having run nothing, **and it ratcheted the committed floor 1155 → 1200**, so every honest run
afterwards would fail a bar the forgery invented).

An attack succeeds — the claim is false — if the gate exits 0 or prints `VERIFY OK`. Six were run,
each a real `scripts/verify.sh` invocation. The floor was read before and after, because raising the
bar is the worse half of D-093's damage.

## Result — 6/6 refused, floor unmoved

```
floor before: 1619

HELD  PY cannot run this project (D-092)          exit=3  REFUSED: /usr/bin/true cannot import hawedit…
HELD  every step replaced with a no-op            exit=5  REFUSED: LINT_CMD FORMAT_CMD TYPECHECK_CMD TEST_CMD overridden…
HELD  the test step alone is replaced             exit=5  REFUSED: TEST_CMD overridden…
HELD  the test step is emptied, not replaced      exit=5  REFUSED: TEST_CMD overridden…
HELD  the test step selects nothing               exit=5  REFUSED: TEST_CMD overridden…
HELD  a forged pytest writes a clean 99,999-test report (D-093)
                                                  exit=3  REFUSED: …cannot import hawedit, or the gate's tools are not its own…

floor after : 1619
6/6 attacks refused
M0.1 HELD
```

Two distinct defences, both doing their documented job:

* **exit 3** — the interpreter probe. `PY=/usr/bin/true` and the forged pytest both fail it, and the
  forgery fails it *by name*: the gate asks where the programs its steps consist of came from, so
  a `pytest` shadowed on PYTHONPATH is not the project's own tool. D-092 and D-093.
* **exit 5** — the override refusal, and `${VAR+set}` catches the *empty* assignment too, so
  `TEST_CMD=` is refused rather than silently replaced by the default. That distinction is
  commented in `verify.sh` and it holds.

The floor did not move under any attack.

## The pass's own first harness was wrong, and said so loudly

The first attempt built the environment as a Python dict and handed it to `subprocess.run`. It
reported:

```
*** FOOLED *** PY is a program that cannot run this project (D-092)
                exit=1  VERIFY OK in output=True
...
*** M0.1's CLAIM IS FALSE ***
```

**That conclusion was false.** On Windows the constructed environment did not reach `bash` the way
the attack intended: the overrides leaked into the *suite's own* gate-invoking tests — the four
"HELD" lines all named `test_nested_full_gate_refuses_instead_of_recursing`, a test failing, not a
gate refusing — and the `VERIFY OK` the harness matched came from somewhere other than a green
verdict. Run directly, the identical attack gives `exit=3` and a `REFUSED` banner with no
`VERIFY OK` anywhere in the log.

It was caught by reading *which* line the harness had matched, rather than trusting the summary it
printed — the same discipline, and the same failure, as the two `pgrep` false positives earlier in
this session, where a pattern matched its own command line.

**Method for later passes:** invoke the thing under attack the way an attacker would — one shell,
directly — and grep the raw log. A harness that constructs the environment is a second program that
can be wrong, and when it is wrong it fails in whichever direction its author was expecting.

## What is still out of reach, and stays recorded

A substituted `hawedit` package itself. D-093 says so plainly and this pass does not change it: the
gate can prove its *tools* are its own, but a `hawedit` that lies about itself is inside the thing
being graded. Named here so 6/6 is not read as "unfoolable".
