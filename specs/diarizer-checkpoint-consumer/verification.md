# Verification Record

2026-10-07, HawaPC01/Windows11 build26300, native CPython3.12.10,
pytest9.1.1, ruff0.9.6, mypy1.15.0, DBOS2.29.0, Torch2.13.0+cpu.
Baseline6c3bdbe. No decoded-media/neural/DER/performance claim from this unit.

Actual seven Serena definition/reference pairs found before edits, source
unchanged. Raw LocalAppData/HawEditEvidence/diarizer-checkpoint-map-20261007/.

Test-first exact whole new module command:
`.venv/Scripts/python.exe -B -m pytest tests/test_pyannote_checkpoint.py --junitxml=C:/Users/Wareen/AppData/Local/HawEditEvidence/diarizer-checkpoint-test-first-20261007.xml -q`.
15 failures/0 errors/skips/15 cases,5.200s. SHA256
`f2bb1e2a26074a348d4aa8c3516fb425411ce4f37c3227574ecb7702f860b4df`.
Includes canonical identity, bypass/corruption and missing held-lock refusals.

Final exact whole adapter modules:
`.venv/Scripts/python.exe -B -m pytest tests/test_pyannote_checkpoint.py tests/test_pyannote_adapter.py tests/test_pyannote_wire.py --junitxml=C:/Users/Wareen/AppData/Local/HawEditEvidence/diarizer-checkpoint-adapter-final-20261007.xml -q`.
34 passes/0 failures/errors/skips,7.478s. SHA256
`3ddd7647a9479fa1d7fa923c063d2e0ae1910c709617bb9320dc14fbb82fddfe`.
All original output assertions retained; temporary opaque file hashes use the
real configured ModelStore verifier. Separate process kernel lock probes cover
import/load/device/inference/conversion and success/failure release. No fake
verification result or inference measurement. Later import observer strengthening
is distinguished from the original test-first body in git/evidence.

Ruff initially found long diagnostic/import placement; strict mypy found a test
namespace mismatch. Corrected formatting and followed existing test_ helper import
pattern. Final lint, strict types and format pass for all four changed Python files.
No harness/model/fixture edits, test skips or assertion weakening. Whole canonical
gate and same-SHA CI remain required; result will be recorded externally after
freezing the local committed candidate. WIP is not a release verdict.
