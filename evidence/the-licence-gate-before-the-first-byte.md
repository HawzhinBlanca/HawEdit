# The NonCommercial gate that runs before a single byte moves, held by nothing

"Pinned and checksummed supply chain" is part of what 10/10 means here. D-139 pinned the gate's
Python packages, D-121 the ffmpeg archive, D-120 made the wheel reproducible. **Model weights are
the largest surface and the last one**: two lines inside heredocs in `scripts/fetch-models.sh`
decide whether multi-gigabyte checkpoints arrive pinned and licence-cleared, and ruff does not
read embedded Python.

## Measured: 3 of 4 held

```
CAUGHT    the download stops pinning the revision (branch head instead)
            tests/test_models.py::test_the_fetcher_passes_the_pinned_revision_to_snapshot_download
CAUGHT    an unpinned repo resolves to main instead of refusing
            tests/test_models.py::test_the_fetcher_refuses_a_repository_that_is_not_pinned
SURVIVED  the NonCommercial gate before the first byte is removed
CAUGHT    revision_for hands back a branch head rather than raising
            tests/test_models.py::test_a_repository_with_no_pinned_revision_is_refused_not_resolved

3/4 caught by the suite as it stands
```

The **pinning** half is well held, and held the right way: `tests/test_models.py` extracts the
real download block from the script and *executes* it against a stubbed Hub, then inspects the
call. That is the pattern D-067 established — an assertion about the text of a command is not an
assertion about what the command does.

The **licence** half had no equivalent. `assert_commercially_usable(entry)`, sitting in the
planning block under the comment *"NonCommercial is a hard reject — checked before a single byte
moves"*, could be deleted with the whole suite green.

## Dead code, or defence in depth?

It cannot fire on the committed tree. `missing_weights()` iterates §7's **production** table, and
D-168's `test_no_registered_model_is_non_commercial` forbids an NC entry there; §7's two
CC-BY-NC-4.0 models live in the exclusion table, which `resolve` refuses.

That makes it defence in depth rather than dead code, and the registry's own docstring says why it
is written the way it is:

> `assert_commercially_usable` keys off the licence, not off those two names, so the next NC
> dependency fails the same way.

The check exists for a §7 that does not yet exist. Defence in depth still has to be shown to work
— and unlike D-166's sibling assertion or D-170's blank clause, **the state here is perfectly
constructible in a test**: the block consumes whatever `missing_weights()` yields.

## The guard

`test_the_fetcher_refuses_a_noncommercial_checkpoint_before_downloading_it` executes the real
planning block with `missing_weights` offering a CC-BY-NC-4.0 entry and requires
`NonCommercialLicence`. Its control,
`test_the_fetcher_plans_a_commercially_usable_checkpoint`, offers an Apache-2.0 entry and requires
the block to *plan* it — without which the first test passes for a block that refuses everything,
and the gate would look present while blocking every model §7 permits.

## One defect of mine, and why it is worth recording

The first version patched `ModelStore.missing_weights` on the class this test module imported.
Other tests in the same file `importlib.reload(hawedit.models)`, so by the time these ran, the
executed block imported a **different class object** — the patch landed on the stale one, the
block read the real §7 table, and the refusal never fired. It passed in isolation and failed in
the file, which is the signature. The helper now resolves `hawedit.models.ModelStore` at call
time.

## Mutation audit — 4/4 lint-clean

```
CAUGHT  the survivor restored: the licence gate is deleted   test_the_fetcher_refuses_a_noncommercial_checkpoint…
CAUGHT  the gate is called but its result ignored            test_the_fetcher_refuses_a_noncommercial_checkpoint…
CAUGHT  assert_commercially_usable stops refusing anything   (that test, plus test_registry's own)
CAUGHT  the gate refuses everything, not only NonCommercial  test_the_fetcher_plans_a_commercially_usable_checkpoint

files restored byte-identical: True
4/4 caught lint-clean
```

The last line is the control doing its job: only the positive test sees a gate that has become
indiscriminate. No production code changed — the check was correct, and now it is held.
