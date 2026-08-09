# Two builds of one commit

> Measured 2026-08-09 on hawapc01 against `450684b`.

`AUDIT_REPORT.md`'s wheel bullet quotes a byte count and says, deliberately, that no SHA-256 is
given: *"The build is not reproducible … A digest here would identify one build at one instant rather
than this code."* That was true, and it is the one line in the supply-chain section that was still
accurate.

## The defect

```
$ pip wheel --no-deps --no-build-isolation -w a .
$ pip wheel --no-deps --no-build-isolation -w b .

a/hawedit-0.1.0-py3-none-any.whl  333,362 bytes  sha256 a7c3b2f1c280aff4…
b/hawedit-0.1.0-py3-none-any.whl  333,362 bytes  sha256 38d1d2475c46e120…
```

One unchanged tree, the same size, different bytes. Nothing sets `SOURCE_DATE_EPOCH`, so every ZIP
entry carries the mtime of the moment it was written. Nothing that leaves this repository could be
identified by a digest, and "pinned and checksummed supply chain" has no checksum to offer.

## The fix, and the same two builds

```
$ git log -1 --format=%ct
1786296162

$ SOURCE_DATE_EPOCH=1786296162 pip wheel … -w c .
$ SOURCE_DATE_EPOCH=1786296162 pip wheel … -w d .

c  333,362 bytes  sha256 c450f9310d956e90dcd4f9c711efd04aa6e1adfacd690d630c9d34988ed4fec2
d  333,362 bytes  sha256 c450f9310d956e90dcd4f9c711efd04aa6e1adfacd690d630c9d34988ed4fec2
identical: True
```

`scripts/build-wheel.sh` derives the epoch from the commit's own author date, so the same commit
yields the same bytes anywhere, and prints the digest. Through the script, twice:

```
hawedit-0.1.0-py3-none-any.whl  333,362 bytes
sha256  c450f9310d956e90dcd4f9c711efd04aa6e1adfacd690d630c9d34988ed4fec2
SOURCE_DATE_EPOCH=1786296162 (commit 450684b)
```

It warns when the tree is dirty — the wheel then is not the commit it is stamped with — and refuses
outside a git checkout rather than falling back to `now`, which is the behaviour it exists to remove.
That refusal is **not tested**: the script finds the repository from its own location, so reaching the
branch means copying the tree out of git, which costs more than three fail-closed lines are worth.

## Proof

Two builds are byte-identical, and — the part that keeps it honest — every ZIP entry is stamped with
the commit's timestamp in UTC. Equality alone would also be produced by a build system that happened
to be deterministic today, so the epoch could be deleted unnoticed; and a control asserting that
setuptools is *non*-deterministic would break the day that stopped being true, which is a check whose
cheapest fix is deleting it.

## The first version of this test was wrong, and only CI could see it

It compared the ZIP stamps against the raw epoch and passed here — because `450684b` happened to
carry an **even** timestamp. The runner's commit was odd, and the test failed by exactly one second:

```
assert {(2026, 8, 9, 17, 43, 52)} == {(2026, 8, 9, 17, 43, 53)}
```

ZIP stores the second as `sec // 2`, so every stamp the format can hold is an even second —
verified directly: writing `second=53` reads back `52`. The expectation now rounds down, which is
not a tolerance but the value the format can represent; a clock-based mtime is wrong by far more
than one second in every entry. The local gate was green on a tree whose HEAD is now odd, and the
same test fails on the pre-fix expectation there too.

Two further instrument errors on the way here, both mine, both caught by reading the raw failure:

* `subprocess.run(["bash", …])` on Windows resolves **WSL's** `bash.exe`, which cannot open a `C:/…`
  path and reported the script as "No such file or directory" while Git Bash ran it. Resolved by
  path now, via `shutil.which`.
* bash eats the backslashes in `C:\Users\…`, so the arguments go in POSIX form.

## The document was stale in three places, and contradicted itself in one

```
revisions.json pinned repositories        6   report: "all five downloaded repositories"
registry entries with a download source   6
unpinned among them                       0   report: pyannote "deliberately unpinned", and
                                               "a test asserts it is the only one"
```

`tests/test_models.py` asserts `unpinned == []` with no exemptions and its comment records that D-075
removed the pyannote exemption as an error rather than a principle. Line 101 also called the model
revisions "unpinned" while line 66 of the same document called them pinned — the correction landed in
one place and not the other, which is the failure this project keeps finding in itself.

Gate: `VERIFY OK — 1270 passed, 0 skipped`.
