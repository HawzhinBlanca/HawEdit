# "Wheel contains …" — and only the tree was ever looked at

`AUDIT_REPORT.md`'s verification evidence says:

> Wheel contains the Kurdish font/OFL, model-source manifest, WSL worker and setup module.
> Verified 2026-08-10 by listing the archive: `assets/fonts/NotoNaskhArabic-Regular.ttf`,
> `assets/fonts/OFL.txt`, `models/revisions.json` + `models/sources.json`,
> `hawedit/asr_worker.py` and `hawedit/wsl_setup.py` …

`tests/test_claims.py::test_the_audit_reports_wheel_contents_claim_names_real_paths` holds it.
Its own docstring says what it holds:

> The files it now names must exist **in the tree that builds the wheel**.

The tree is not the wheel. `assets/` and `models/` are not Python packages — they reach the
archive only through `[tool.setuptools.data-files]`.

## The premise, checked on the artifact first

Built from `bed2176` with `scripts/build-wheel.sh` and listed:

```
hawedit-0.1.0-py3-none-any.whl  352,754 bytes  55 entries

  PRESENT  assets/fonts/NotoNaskhArabic-Regular.ttf   hawedit-0.1.0.data/data/share/hawedit/assets/fonts/NotoNaskhArabic-Regular.ttf
  PRESENT  assets/fonts/OFL.txt                       hawedit-0.1.0.data/data/share/hawedit/assets/fonts/OFL.txt
  PRESENT  models/revisions.json                      hawedit-0.1.0.data/data/share/hawedit/models/revisions.json
  PRESENT  models/sources.json                        hawedit-0.1.0.data/data/share/hawedit/models/sources.json
  PRESENT  hawedit/asr_worker.py                      hawedit/asr_worker.py
  PRESENT  hawedit/wsl_setup.py                       hawedit/wsl_setup.py
```

**The claim is true.** All six ship; the four data files land under
`hawedit-0.1.0.data/data/share/hawedit/…`. Still 55 entries; the byte count has moved from the
**346,694** D-141 recorded to **352,754**, which is a dated measurement doing what the report's
first bullet says dated measurements do, not a drift.

So there was nothing to repair. What there was, was nothing holding it.

## What was already held, and what was not

`tests/test_claims.py::test_every_data_file_the_wheel_ships_is_tracked_by_git` reads the same
pyproject stanza and requires every path in it to be tracked by git. It catches the stanza being
**emptied** — `assert shipped` fails. It does not look at an archive, and it says nothing about
*which* files the stanza should contain.

Measured, one file at a time, whole suite each, baseline verified green first:

```
CAUGHT    the data-files stanza is deleted
            tests/test_build.py::test_the_wheel_contains_every_file_the_audit_report_says_it_does
            tests/test_claims.py::test_every_data_file_the_wheel_ships_is_tracked_by_git

CAUGHT    only the OFL licence is dropped from the stanza
            tests/test_build.py::test_the_wheel_contains_every_file_the_audit_report_says_it_does

CAUGHT    a second licence-bearing asset the claim does not name
            tests/test_build.py::test_the_wheel_contains_every_file_the_audit_report_says_it_does
            tests/test_claims.py::test_every_generated_attribution_notice_appears_in_the_readme
            tests/test_claims.py::test_every_readme_attribution_bullet_is_generated
            tests/test_claims.py::test_the_readme_states_the_same_licence_the_notice_does

files restored byte-identical: True
3/3 caught lint-clean
```

**The second one is the finding.** Before today, deleting one line from the stanza —

```toml
    "assets/fonts/OFL.txt",
```

— shipped every wheel without the licence OFL-1.1 requires to accompany the font, with the whole
suite green. The pre-existing stanza test still passes, because what remains is still tracked.
Both tree-level tests still pass, because **the file is still in the tree**: they cannot see this
failure by construction, which is also why no paired demonstration is needed to establish that
reading the archive is what does the catching.

`registry.SHIPPED_ASSETS` records that obligation with the path
(`licence_file="assets/fonts/OFL.txt"`) and `tests/test_claims.py` asserts the file exists beside
the font. The thing that ships is the archive.

The first mutation is caught two ways and one of them is pre-existing, so it is not evidence for
the new test. It is reported as measured rather than as a win.

## The guard

`tests/test_build.py::test_the_wheel_contains_every_file_the_audit_report_says_it_does` builds a
wheel with the same `build()` helper the reproducibility tests use and requires every path the
report's own bullet names to be in the archive. The list is **read out of the claim** rather than
copied beside it, so the test cannot drift from the sentence it is holding.

Non-vacuity comes from a *different file* than the one being parsed: the licence files in
`registry.SHIPPED_ASSETS` must be among the paths the claim names. A reworded bullet that stopped
naming `OFL.txt` fails here rather than quietly checking nothing — and the third mutation shows
the binding is live, since adding a second licence-bearing asset the claim does not name reddens
it.

## One mutation attempted and discarded

A fourth mutation would have paired "the stanza is deleted" with "the check reads the tree instead
of the archive", to demonstrate the archive read is load-bearing. It came back **lint dirty**, so
it measured ruff (D-148, D-150) and is not reported as a result. It was also unnecessary: mutation
2 leaves the file in the tree untouched, so a tree-reading check cannot see it, which is the same
conclusion from data already in hand.
