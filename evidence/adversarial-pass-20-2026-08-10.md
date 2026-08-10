# Adversarial pass #20 — M2.8's credential panel and billed judge

> Measured 2026-08-10 on hawapc01 against `0e1ad43`.

M2.8 is **DONE** for *"Gemini credential panel + the real §3 Stage 4 judge"*, and the cell claims:
the panel *"verifies a key against Google before storing it, refuses any target git tracks, and
never prints it"*; the judge has *"schema-enforced output, real `countTokens` before the billed
call, temperature 0, bounded retries on transient failures only, and §3's ZDR gate as a required
value"*. One mutation per claim.

## The claim it leads with had no test

```
$ grep -n "credentials.main\|main(\[" tests/test_credentials.py
(nothing)
```

`main()` is where "verify, then store" is sequenced, and nothing drove it. Two mutations survived:

```
SURVIVED  a key that Google rejected is stored anyway
SURVIVED  the key is stored before it is verified
```

The units around it were well tested — `validate_gemini_key` against four transports,
`write_credential` against symlinks, hardlinks, tracked paths and permissive modes, `mask` against
two keys — and the gap was exactly between them.

Four tests now drive the panel with the network and the writer replaced by recorders. The ordering
one asserts `order == ["validate", "write"]`, because asserting only that the key *was* stored is
satisfied by a panel that stores first.

## The TOCTOU half of the O_NOFOLLOW reconstruction was untested

```
os.O_NOFOLLOW present: False
_O_NOFOLLOW value on this machine: 0
=> the identity test DOES run here (it is gated on not _O_NOFOLLOW): True
```

```
SURVIVED  the opened file is not proved to be the file that was checked (TOCTOU)
```

The pre-open symlink refusal had a test; the "same file after the open" comparison did not — on the
one platform where it runs. The race is forced by making `os.lstat` answer about a different file,
which is what an attacker replacing `.env` between the two calls achieves.

## Two survivors were platform artefacts, measured not assumed

```
mode of a file created with 0o666 on Windows: 0o666
mode of a file created with 0o600 on Windows: 0o666
_O_NOFOLLOW value on this machine: 0
```

So `0o600 → 0o666` is **unobservable** here and removing `_O_NOFOLLOW` from the open flags is a
**no-op**. Both properties are held on this platform by the pre-open refusal and by
`assert_owner_only`'s ACL read, whose mutations are caught. Dropped from the audit with the
measurement recorded, rather than reported as holes.

## One mutation of mine was wrong

`if attempt < self._max_attempts:` → `if True:` was labelled "retries are unbounded". The loop is
bounded by `for attempt in range(1, self._max_attempts + 1)`; that line only skips the final sleep.
The bound is tested — `test_a_rate_limit_is_retried_and_then_given_up_on` asserts exactly **3**
`generateContent` calls. Replaced with a mutation that raises the ceiling; caught.

## The audit was contaminated by the guard it was auditing

First run: 18/20, with **sixteen** REDs all naming `test_writing_to_a_tracked_path_is_refused` —
every mutation after the git-ignore one.

```
$ git status --short
 ?? a-credential-must-never-be-written-here.env
$ cat a-credential-must-never-be-written-here.env
# hawedit credentials. Git-ignored. Never commit this file.
GEMINI_API_KEY=AIzaSy-not-a-real-key-0000-abcd
```

The git-ignore mutation made the guard fail open; the test wrote its probe file; and that test's
**first** assertion is that the probe does not exist. One fail-open became an indefinitely red suite
that only a manual `rm` of a real-looking credential file could clear — and every later mutation was
red for the wrong reason.

D-113 chose one stray file over a deleted test, and that was right. It did not make the file
self-healing. Removed in `finally` now, with a pre-existence message naming what to inspect. The
check is unchanged.

## Proof

```
baseline green: True

RED  a key that Google rejected is stored anyway
RED  the key is stored before it is verified
RED  validation calls the API with the key in the URL instead of a header
RED  a non-200 from the API counts as a valid key
RED  the git-ignore check is skipped
RED  a caller-supplied path defaults to NOT checking git
RED  the mask returns the secret whole
RED  the pre-open symlink refusal is dropped on platforms without O_NOFOLLOW
RED  the opened file is not proved to be the file that was checked (TOCTOU)
RED  a hardlinked .env is written through (the review-2 bug)
RED  the write truncates at open, before the identity checks can run
RED  the billed call happens without counting tokens first
RED  the counted total is not checked against §3's tier ceiling
RED  the judge samples instead of running at temperature 0
RED  the response schema is not enforced on the model's output
RED  a 400 is retried, billing twice for the same malformed request
RED  the retry ceiling is raised
RED  confidential material is uploaded without zero-data-retention

18/18
restored and green: True
```

## What survived the pass

**Everything in `gemini.py`.** All the judge's claims — schema-enforced output, `countTokens` before
the billed call, the tier ceiling, temperature 0, no retry on a 400, a bounded retry ceiling, and
the ZDR gate — redden when reverted. So do every `write_credential` guard the two independent
reviews added, except the identity test above. The failures were in the panel that sequences them
and in the test that guards the sequence.

Gate: `VERIFY OK — hawedit gate green`, 1373 tests.
