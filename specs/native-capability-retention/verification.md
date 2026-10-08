# Verification

Baseline current clean gate and actual Windows red/probe/Serena provenance in
research.md. Hardware HawaPC01 Windows11-10.0.26300, Python3.12.10,
pytest9.1.1/ruff0.9.6/mypy1.15.0/DBOS2.29.0. This is native fault handling,
not model/GPU/editorial or first-reviewable-clip performance acceptance.

Tracked five-case valid behavioral red:0pass/5fail/0error/skip,
HawEdit-native-capability-tracked-red-20261008.xml,
SHA256298e104c50f25e767922d049786fee59c00d15b77eb16c35442df0cbcdf03cb7.
Initial repaired five cases pass, JUnit391b148780027b37ba73ac4d562bc70569c4d96b58b71e71b51860e3f0a851f8.
Full strict types364files pass. Initial lint correctly refused import order and
embedded-code line lengths; only formatting corrected, not assertions/expected
outputs. Actual new-test definition/reference map unchanged before correction,
5eb81a10f22d4bf70abea2443779fa7f2e51a7d8fd9e7bca3185ae1aebc7107e.
Whole affected suite/final static/exact committed full gate pending.
No task/ledger/CI/security/release promotion.

Final complete 12 affected modules:396pass/0failure/error/skip,345.645s JUnit,
HawEdit-native-capability-affected-20261008.xml,
SHA25684b0e580312086a33cb7fb9ac744f0b3a0bb124d5590634e57751b0e5bb52a40.
Full ruff/format/strict types364files pass; git diff --check clean. Original
pytest42396/launcher60608/pwsh41176 absent before session61075 closed.
Five actual faults additionally pass restored-fault close refusal, new-create
refusal, exact original image/handle retention and GC survival. Parent fault
owners remain isolated; no actual Linux/GPU/provider model calls certified.
Local reviewed commit and exact frozen clean full gate follow; not CI acceptance.
