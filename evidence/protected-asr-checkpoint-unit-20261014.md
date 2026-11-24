---
commit: 9e6b17a0ae8ed0af1cc0d94a288afd3bdf291b07
media_sha256: n/a (generated PCM and explicitly controlled speech for protocol contracts)
host: HawaPC01, Threadripper3990X, Windows26300, CPython3.12.10, pytest9.1.1, ruff0.9.6, mypy1.15.0
command: .venv/Scripts/python.exe -m pytest tests/test_asr_checkpoint.py tests/test_asr_resume.py tests/test_worker_publication.py tests/test_worker_publication_collisions.py tests/test_asr_stop.py tests/test_asr_origin.py tests/test_adapter_identity.py tests/test_asr_model_lifecycle.py tests/test_asr_completion.py tests/test_asr.py tests/test_claims.py --junitxml=C:/Users/Wareen/HawEditCheckpoint-final-callers-20261014.xml
status: WIP; parent SHA plus scoped working changes, not a full gate, model result or completed producer
---

# PA3 Shared Inference And Host Checkpoints

Authority: approved protected-asr-producer/plan.md, D-329. Actual unchanged
Serena five-pair caller map is verified in checkpoint-research.md before edits.
New remote protocol uses the same canonical inference and existing durable
OperationJournal; no model substitution, installation, cloud call or spending.

Red collection: missing asr_checkpoint module; raw external report retained at
C:/Users/Wareen/HawEditCheckpoint-red-20261014.xml. First caller run236passed,
two Windows setup/teardown errors because a65KiB test parameter generated an
oversized PYTEST_CURRENT_TEST environment variable. Short IDs preserve the
exact oversized input. Another new-test assertion used text_raw rather than
RawTranscript.text_ckb and was corrected; no production/test assertion weakened.

Final scoped322passed, zero failed/errors/skips,53.56s. Includes36 new protocol
tests and every existing caller module from the actual map, plus claims checks.
External raw XML SHA256:
e9068749ea389f99cc6b189fcf74274d02705b5d8676a1d2742c67ad7492d79d.
Final exact fast command passes lint and strict mypy413files. This is not the
full gate; its raw log is C:/Users/Wareen/HawEditCheckpoint-final-fast-20261014.log.

Real OS pipes, real generated WAV files, actual owner-private leased journal
and atomic writes show restart recovery, ACK-after-save and unchanged worker
files. Explicit controlled backend text does NOT establish accurate ASR or
protected GPU execution. Large exact Sorani UTF-8 result uses32KiB binary
chunks inside64KiB JSON frames,16MiB total bound, durable chunks and final
size/hash/media record. Invalid sequence, binding, clocks, audio hashes, JSON,
oversized/truncated frames, missing lease and damaged/incomplete result refuse;
failed sessions cannot continue. CLI exclusive publication and adapter/origin/
validation/alignment/fail-stop caller tests remain green, unchanged assertions.

The new pending private result is NOT pipeline completion/publication. Stream
hashes are NOT endpoint authentication. Original launch-owned channels,
deadlines/drain, full content-hashed runtime/model/driver closure, actual
production resources/effects, current independent VEX and protected builder/
DBOS adoption remain necessary. No receipt is forged and no legacy subprocess
is used to obtain a transcript. No new ZAR transcript or reel is claimed.
Exact full gate and same-SHA CI remain required; no ledger row is promoted.
