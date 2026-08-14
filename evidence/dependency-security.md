# Dependency security audit — 2026-08-09

## Finding

The clean Python 3.12 install of HawEdit revision `53ecc475b7db` contained
`fonttools==4.55.3`. A path-scoped audit with `pip-audit==2.10.1` reported
CVE-2025-66034, fixed in 4.60.2. The upstream advisory identifies the affected
range as `>=4.33.0,<4.60.2` and describes path traversal/arbitrary file writes
through malicious designspace input:

- <https://github.com/fonttools/fonttools/security/advisories/GHSA-768j-98cg-p3fv>
- <https://github.com/fonttools/fonttools/releases/tag/4.60.2>

The baseline audit also reported vulnerabilities in the virtual environment's
bootstrap `pip==25.0.1`. `pip` is not declared by HawEdit and is not present in
the wheel's `Requires-Dist`; the validation environment was upgraded to
`pip==26.2.1` before measuring the corrected dependency set.

## Fix

- `pyproject.toml` now requires exactly `fonttools==4.60.2`.
- The WSL Stage 1 provisioner uses the same exact version in both its `uv` and
  standard-`pip` branches.
- `tests/test_dependency_security.py` refuses a vulnerable base version, a
  non-exact range, a missing/duplicated pin, or WSL/base version drift.

Exact pins are deliberate: the build and clean installation must be
reproducible, while accepting all future versions would turn a CVE floor into
an unreviewed compatibility decision.

## Independent compatibility and vulnerability check

A fresh environment at `.gate/fonttools-4.60.2-compat` was created with Python
3.12 and upgraded to `pip==26.2.1`. Installing the edited project resolved:

```text
fonttools 4.60.2
klpt 0.1.7
chunspell 2.0.1
```

Measured checks:

```text
python -m pip check
No broken requirements found.

assert_font_covers_kurdish(assets/fonts/NotoNaskhArabic-Regular.ttf)
PASS

pip-audit==2.10.1 --path .gate/fonttools-4.60.2-compat/Lib/site-packages
No known vulnerabilities found
```

`pip-audit` skipped the local editable `hawedit` distribution because it has no
public index version; it audited the resolved third-party environment. This is
a dated result and must not be read as protection against future advisories.

## Mutation evidence

Each source mutation was run against `tests/test_dependency_security.py` and
then restored:

1. `fonttools==4.60.2` → `fonttools==4.55.3`: caught by the fixed-version floor.
2. `fonttools==4.60.2` → `fonttools>=4.60.2`: caught by exact-pin parsing.
3. WSL constant `4.60.2` → `4.55.3`: caught by cross-environment equality.

Result: **3/3 caught**. Focused compatibility/security suite after restoration:
**71 passed**, with Ruff, format, and mypy clean for the changed Python files.
