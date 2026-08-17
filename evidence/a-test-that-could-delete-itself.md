# A test that could delete itself

> Measured 2026-08-09 on hawapc01 against `cca72fe`.

D-137, D-143 and D-147 were the same shape: a guard function is unit-tested, and the single call site
that reaches it can be neutered with the suite staying green. Three is a pattern, so this iteration
swept for the rest deliberately instead of waiting for a fourth adversarial pass.

## The sweep, and its answer

For every `assert_*` in `src/hawedit`, find its call sites in `src/`; where there is exactly one,
replace that call with `pass` and run the suite.

```
16 single call sites, one at a time

CAUGHT  assert_captions_within_clip   assert_contiguous          assert_encoded_span
CAUGHT  assert_frames_reached_model   assert_fully_loaded        assert_ignored_by_git
CAUGHT  assert_one_hardware           assert_registry_excludes…  assert_rtl_stack
CAUGHT  assert_sv6d_within_window     assert_time_contiguous     assert_timestamps_span_window
CAUGHT  assert_tools_are_from_…       assert_window_coverage     assert_within_asr_ceiling
SKIPPED assert_devices_available (multi-line call, not neuterable by line replacement)

unprotected call sites: 0
```

**The pattern is not systemic.** The three earlier findings were real and are fixed; there is no fourth
wave.

## The first run said 9, and all nine were false

It judged pytest by `re.search(r"^FAILED |failed", stdout)` rather than by the exit code. Checking one
result by hand — `assert_tools_are_from_this_environment`, which is D-093's own claim — showed
neutering it fails **three** tests including `test_a_forged_test_report_cannot_produce_a_green_gate`.
The instrument was wrong, not the code.

That is the same error as reading a CI run's step text instead of its `conclusion` field, made a second
time in this project. The sweep now raises on any exit code that is neither 0 nor 1.

## What the sweep broke, and the real finding

Neutering `assert_ignored_by_git` for one run destroyed `tests/test_credentials.py`. Its own test
pointed a real credential writer at `Path(__file__)`:

```python
tracked = Path(__file__).resolve()  # this test file is committed
with pytest.raises(CredentialError, match="not ignored by git"):
    write_credential(GEMINI_API_KEY, FAKE_KEY, env_file=tracked)
```

With the guard failing open, `write_credential` did its job: 262 lines became eleven `KEY=VALUE`
fragments scavenged from the module it had overwritten, under the header *"hawedit credentials.
Git-ignored. Never commit this file."* Restored from HEAD; nothing reached a commit.

The guard itself is sound — it fails **closed** in every direction, including when git is missing
(`OSError` → `CredentialError`). The hazard was the test making the subject under test the only barrier
between the suite and its own source.

## The fix, and the proof

The target is now a path that does not exist and is not ignored. `git check-ignore` answers from
`.gitignore` patterns, not the filesystem, so the refusal is identical:

```
nonexistent, non-ignored path -> check-ignore exit 1   (guard refuses)
a gitignored path             -> check-ignore exit 0   (guard allows)
```

With the guard neutered **by line number** — because `if result.returncode != 0:` appears twice in
`credentials.py`, and a text replace hit the wrong one first, reporting a pass that measured nothing:

```
the guard fails open                 : test FAILS (caught)
test source still intact             : 280 lines   (before: 262 -> 11)
damage                               : one 109-byte stray file
```

Two assertions bracket the call — the probe must not exist before, and must not exist after — so a
refusal arriving *after* the write would be caught too.

Gate: `VERIFY OK — 1231 passed, 0 skipped`.
