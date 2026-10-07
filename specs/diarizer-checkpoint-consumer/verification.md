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

## Whole-Suite Reload Failure And Repair

The frozen f083a896f9f30eac74a3767534e8517218a5a12f exact canonical gate
finished RED:5260 cases,5251 passed,9 failed,0 errors/skips. JUnit2569.501s,
controller2577.1878125000003s on the native host/versions above; source unchanged.
Eight failures are checkpoint-refusal exception identities after real model module
reloads; the ninth is the independent current security-review policy refusal.
Raw C:/Users/Wareen/AppData/Local/HawEditEvidence/diarizer-checkpoint-gate-20261007/.
JUnitSHA256 `2d450f1f63197b264a63e135a5ab303be9b858b49c75e15f65ace19f5813cc5d`.
The earlier34-case isolated pass did not establish whole-suite integration.

Actual whole models/adapter/checkpoint/wire reproduction before repair:138 cases,
131 passed,7 failed,0 errors/skips,12.204s JUnit. Raw
HawEditEvidence/diarizer-model-reload-diagnostic-20261008/; JUnitSHA256
`f785152ecd2aa15fcb390c6a41b7ac18ea2fafa877719e8a809ce5440dda936e`.
Fresh seven-pair actual Serena definition/reference map before edits is retained
in HawEditEvidence/diarizer-reload-map-20261008/serena-map.json.

The real subprocess reload regression first failed externally against unchanged
production, then its same body was adopted before production repair. Whole source
checkpoint module:16 cases,15 passed,1 new failed,0 errors/skips. JUnit
HawEditEvidence/diarizer-reload-source-test-first-20261008.xml; SHA256
`93c4b60af9806f914441139e9d6a038fb9355e10b67d6dc467208d9d996fdaf5`.
It actually reloads models in an independent Python process, verifies changed
class identity and invokes real checkpoint access; no verifier/reload/error mock.

After module-bound access/errors repair, exact whole four-module command:
`.venv/Scripts/python.exe -B -m pytest tests/test_models.py tests/test_pyannote_adapter.py tests/test_pyannote_checkpoint.py tests/test_pyannote_wire.py --junitxml=C:/Users/Wareen/AppData/Local/HawEditEvidence/diarizer-reload-whole-model-adapters-final-20261008.xml -q`.
139 passed,0 failures/errors/skips,10.102s JUnit. SHA256
`a1a65ee34401f39bf13716cb39a612102fc71a91f711fed4b69ba0ea6301a9de`.
Existing reload/refusal/output/hash/lock assertions are retained. Lint and strict
types pass for both changed Python files; ruff formatting applied to the adapter.
Whole caller diagnostics and the next frozen clean-source full gate are separate
required evidence, not inferred from this139-case diagnostic. No neural, VEX,
CI, publication or complete-system verdict is granted by the repair.

Whole actual ingest/pipeline/claims caller diagnostic after repair:
`.venv/Scripts/python.exe -B -m pytest tests/test_ingest.py tests/test_pipeline.py tests/test_claims.py --junitxml=C:/Users/Wareen/AppData/Local/HawEditEvidence/diarizer-reload-callers-20261008.xml -q`.
448 passed,0 failures/errors/skips,534.724s JUnit on recorded native host. SHA256
`52d2d51662a7524613a4fb38be9dd73f190b092395e073bbbfed4442779d7688`.
No selectors, removed/changed assertions, skip or inference-quality claim. The
separate exact clean-commit canonical gate remains required; WIP remains WIP.
