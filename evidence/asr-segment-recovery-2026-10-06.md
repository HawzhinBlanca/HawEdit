# ASR Segment Recovery Engineering Checkpoint

```yaml
commit: f18a0d6bc54af959c841d7f33ba72a529f3ead32
media_sha256: bd004519e4ed0254f5c4f5197aa501acc56ce957829f62ac0bdc4d7190ec1dd2
host: HawaPC01
command: .venv/Scripts/python.exe -B -m pytest tests/test_asr_resume.py tests/test_asr.py tests/test_asr_stop.py tests/test_asr_completion.py tests/test_adapter_identity.py tests/test_asr_worker_diagnostics.py --junitxml=C:/Users/Wareen/asr-resume-frozen-components.xml -q
```

Baseline 422a3be82b659c09f1d653c59458ee12aafa058b; D-284;
specs/asr-segment-checkpoints. Owner-approved Phase 2 recovery repair, not acceptance.

Fresh source-bound ZAR38 attempt: exit 1, existing WSL bridge timeout 19020 s,
controller 19201.437921 s. Canonical inference returned before independent
validation, observed through read-only stacks. No worker output/raw transcript
or video was saved. All owned processes closed; source and input hashes unchanged.
Private terminal: asr-context-producer-20261006/full-source-retest/terminal.json;
stderr SHA256 3cdbd34dad426e54725049f869e3de4d9af31ccebaa72702c608d628aaf01592.
This is a failed full-source attempt, not a full ASR pass or throughput benchmark.

Repair: native Linux owner-private fsynced operation journal, nonblocking writer
lease, explicit whole-request/source/runtime/model/PCM bindings, separate draft,
validator and correction-alignment records. Global routing, first-failure halt,
decoder/model/stopping policy and finite timeout remain unchanged. No cache is
a completed stage, canonical raw file, review signature or publication certificate.

Test-first missing-module collection error retained in tool history. Initial
component checks were superseded after additional drift/schema protections;
only the final unchanged-code run below supports this component claim.

Final frozen-code command: native venv Python -B -m pytest tests/test_asr_resume.py tests/test_asr.py
tests/test_asr_stop.py tests/test_asr_completion.py tests/test_adapter_identity.py
tests/test_asr_worker_diagnostics.py --junitxml=C:/Users/Wareen/asr-resume-frozen-components.xml -q.
Actual JUnit: 158 tests, zero failures/errors/skips, 34.223 s.
Twenty-one new checkpoint cases include abrupt subprocess exit, refusal of changed
bound PCM, damaged/linked records, storage failures, concurrent writers and
controlled worker validation recovery without repeating drafts. Actual storage
and decoded WAV are used; injected model responses are NOT model-quality evidence.
Production model binding is not mocked in the actual CLI; its real-media test
is still required. The controlled worker integration isolates composition only.

Hardware/software: HawaPC01/Windows build 26200, CPython 3.12.10, pytest 9.1.1,
ruff 0.9.6, mypy 1.15.0, DBOS 2.29.0. No GPU model inference in component tests.
The prior 157-case run is superseded after adding final-operation binding-drift refusal.
JUnit SHA256: ecaf9e377b023c2c6ddf1120c613be8e83278a292f5f6ce84ebc2dbbccdc0698.
Log SHA256: db147ac21aac6ba5fd2819bbadf1dacee80393db201dc10cbcd1147a96a6cc77.
Exact fast command bash scripts/verify.sh --fast exits 0: all lint and strict
type checks pass, 325 files. Fast-log SHA256:
623bc3f86c8972034f7198a0c48a610595992593920da1712c5dc64b8cb0dfa7.
Fast checks are NOT the full gate. Format and diff checks pass on edited source.

The first exact f18a0d6 full gate exits 1: 4930 passed / four failures, 2273.21 s.
Three documentation omissions are corrected: this required evidence header,
README module map and an explicit WIP module ledger row. The fourth remains
the historical VEX binding. No harness/assertion change or status promotion.
Current-SHA gate rerun and supported real retest remain pending. Earlier
422a3be full gate had 4912 passed / one stale VEX binding failure (#24), not green.
Qualified current security review, adapted-loader held-descriptor repair, native
fidelity, isolated performance, full reel delivery, CI and sustained acceptance
remain open. No ledger promotion, push, spending, publication or 10/10 claim.
