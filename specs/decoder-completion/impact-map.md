# Caller Impact Map

Actual Serena mappings at clean 6df0998 are cited in research.md. New symbols
have no existing callers. Existing definitions and references were read first.

| Symbol | Affected callers | Verification |
|---|---|---|
| OmniAsrBackend.transcribe_segment | OmniAsrAdapter, prepared production segments, direct parallel test | completion contracts, ASR, ASR stop, adapter identity, real integrated probe |
| OmniAsrBackend._load | backend inference/realignment and adapter identity tests | no loader/model changes; preserve parallel forward test |
| OmniAsrProducer | pipeline producer construction, readiness, ASR tests | separate optional admission identity, fake backend cannot claim canonical guard |
| WslOmniAsrProducer | shared builder, CLI, host worker bridge, ASR/adapter/stop tests | same policy as native canonical backend; source-bound runtime |
| TranscriptStore.reusable_raw | run_pipeline and transcript tests (15 reference occurrences) | optional keyword preserves legacy callers; required policy refuses old/malformed/mismatched records |
| TranscriptStore.write_raw | pipeline and ASR/stop/audit/pipeline/review/transcript tests (53 occurrences) | optional keyword; no rewrite of old raw or provenance on collision |
| run_pipeline | CLI/shared builder/web and pipeline/episode/checkpoint/events/ingest/render/review/cost/screener tests (197 occurrences) | pass actual policy through read/write; integration tests ensure refusal before ASR |
| transcribe_prepared_segments / run_request | native producer, WSL worker and ASR/stop/adapter tests | existing first-failure behavior; incomplete cause preserved, no later work/output |

No signatures of existing positional arguments change. No supplied transcript
becomes verified by a policy label. No parser preset, cloud authority, rendering,
publication or reviewer implementation changes in this unit.
