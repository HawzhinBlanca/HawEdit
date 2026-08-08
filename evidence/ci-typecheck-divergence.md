# `verify.sh` printed VERIFY OK here and the runner failed on four of my own lines

> Measured 2026-08-08 on hawapc01 and against GitHub Actions run `31261246630`.

The `gh` CLI became available this afternoon, which made the remote gate visible for the first
time. It had been red since 14:07.

## What the runner said

```
==> lint
All checks passed!
==> typecheck
src/hawedit/video_input.py:302: error: Cannot find implementation or library stub for module
    named "PIL"  [import-not-found]
src/hawedit/video_input.py:329: error: Cannot find implementation or library stub for module
    named "transformers.models.qwen3_vl.video_processing_qwen3_vl"  [import-not-found]
src/hawedit/qwen_visual.py:120: error: Cannot find implementation or library stub for module
    named "transformers"  [import-not-found]
src/hawedit/qwen_visual.py:137: error: Unused "type: ignore" comment  [unused-ignore]
Found 4 errors in 2 files (checked 94 source files)
##[error]Process completed with exit code 1.
```

All four lines are mine, added across iterations 8–12. I never saw them because I never pushed.

## Why the two disagree

CI installs `.[dev,media]` and deliberately not `gpu` — the workflow says so: *"CPU wheels: §6
puts Stage 0 on CPU by design, and the CUDA build of torch is ~2 GB of runner disk for kernels
nothing here calls."* So `transformers` and `pillow` are present on hawapc01 and absent on the
runner, and `mypy --strict` is therefore checking **two different programs** in the two places.

The fourth error is the same fact seen from the other side, and it is the more interesting one:
`# type: ignore[no-untyped-call]` is *required* where transformers is installed (it ships
`py.typed` and leaves `AutoProcessor.from_pretrained` untyped) and *forbidden* where it is not
(the module is `Any`, the call is fine, and `warn_unused_ignores` fires). No single annotation
satisfies both, which is why the fix is not another ignore.

## Reproduced locally, exactly

`mypy --no-site-packages` makes the type checker behave as if the packages were absent:

```
$ mypy --strict --no-site-packages src/hawedit/video_input.py src/hawedit/qwen_visual.py
video_input.py:302  Cannot find implementation or library stub for module named "PIL.Image"
video_input.py:302  Cannot find implementation or library stub for module named "PIL"
video_input.py:329  Cannot find implementation or library stub for module named
                    "transformers.models.qwen3_vl.video_processing_qwen3_vl"
qwen_visual.py:120  Cannot find implementation or library stub for module named "transformers"
qwen_visual.py:137  Unused "type: ignore" comment
```

The same four, byte for byte, without pushing anything.

## The fix

**`transformers.*` and `PIL.*` join the `ignore_missing_imports` override list.** That list
already exists and already holds `torch.*`, `klpt.*`, `scenedetect.*`, `silero_vad.*` and the
rest — these two were simply never added. Every import of them is already inside a function
behind `try: … except ImportError`, which is what makes them optional at runtime; the override
is the same statement to the type checker.

**The environment-dependent ignore is removed rather than moved.** Binding the loader through
an explicitly-`Any` local says the same thing in both environments:

```python
load_processor: Any = AutoProcessor.from_pretrained
processor = load_processor(str(model_dir), trust_remote_code=trust_remote_code)
```

Verified both ways: `--no-site-packages` reports 0 of the four, and with the packages installed
mypy reports `Success: no issues found in 2 source files`.

## The check that would have caught it here

`tests/test_claims.py` now runs the real type checker in the runner's condition —
`mypy --strict --no-site-packages` over the two modules that import the extra — and asserts exit
0. Scoped to those two files on purpose: run over all of `src`, `--no-site-packages` is
*stricter* than CI, because CI installs `media` and so `numpy` and `cv2` resolve there. An
override for `numpy` would discard the stubs it ships and with them real type coverage.

## Two things this took to get right, both worth recording

**The first version of this test was indirect and wrong.** It parsed `pyproject.toml`, mapped
distribution names to import names, and asserted each was in the override list. It passed while
the real condition still failed. An assertion about configuration is not an assertion about the
type checker — which is precisely the mistake this whole finding is about, made again one layer
up. Replaced with the direct invocation.

**The second version passed for a worse reason: `.mypy_cache`.** The subprocess reused
incremental state written by the ordinary gate typecheck, which ran *with* the packages
installed, so removing an override changed nothing it could see. Found by mutating the override
away and watching the test stay green. `--no-incremental` is not a tidiness flag here; without it
the test reports a verdict about a run that never happened.

## Mutation audit, against a baseline verified green first

```
baseline: GREEN
CAUGHT  the transformers override
CAUGHT  the PIL override
CAUGHT  the Any-typed loader binding

3/3
```

## What this says about the project's own DONE rule

The rule is "code + test + gate green + evidence", and `BLOCKED.md` #7 has said since it was
written that the second half of it — *"required CI checks green"* — "currently refers to
nothing", because the workflow runs but does not block. This is the first time that gap has been
measured rather than described: the local gate was green and the remote one was red for three
hours, and nothing in the repository could tell.
