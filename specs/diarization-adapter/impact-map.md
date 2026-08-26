# Impact map — pyannote diarization adapter

Callers from `find_referencing_symbols`. Nothing here changes an existing signature; the two
touched functions gain optional arguments with today's behaviour as the default, so every caller
below must keep passing unchanged.

## `build_parser` — `pipeline.py:2242` (gains `--diarize`, `--diarize-device`)

| caller | site | covered by |
|---|---|---|
| `pipeline.main` | `pipeline.py:2406` | `test_pipeline.py` CLI suite |
| `durable.main` | `durable.py:47` | `tests/test_durable.py::test_run_durable_reports_the_same_thing_a_direct_call_would` |
| `durable_workflow._run_pipeline_step` | `durable_workflow.py:137` | same test (drives `_build_and_run` through the DBOS step) |
| `test_the_cli_defaults_put_each_visual_model_where_section_6_puts_it` | `test_pipeline.py:2017` | itself |
| `test_the_composer_wires_each_model_to_the_device_section_6_assigns` | `test_pipeline.py:2094` | itself |
| `test_the_default_run_still_plans_at_section_3s_ceiling` | `test_pipeline.py:2168` | itself |

A new flag defaulting to off is invisible to all six. **T1 adds
`test_the_default_run_does_not_enable_diarization` so that stays true by assertion, not by luck.**

## `_build_and_run` — `pipeline.py:2419` (constructs the diarizer)

| caller | site | covered by |
|---|---|---|
| `pipeline._run_from_args` | `pipeline.py:2610` | `test_pipeline.py` CLI suite |
| `durable_workflow._run_pipeline_step` | `durable_workflow.py:137` | `test_durable.py::test_run_durable_reports_the_same_thing_a_direct_call_would` |
| `test_run_durable_reports_the_same_thing_a_direct_call_would` | `test_durable.py:198` | itself |

This test asserts the durable path and the direct path agree. It is the one that would catch a
diarizer wired into `main` but not into `_build_and_run` — the exact shape of the existing bug
where `run_pipeline` accepts `diarizer=` and no CLI ever passes it.

## `attach_diarization` — `ingest.py:688` (**unchanged**, newly exercised by a real producer)

| caller | site | covered by |
|---|---|---|
| `run_pipeline` | `pipeline.py:1359` | `test_pipeline.py` diarization suite |
| `test_diarization_attachment_records_a_sorted_exclusive_result` | `test_ingest.py:444` | itself |
| `test_diarization_attachment_refuses_untrusted_invalid_output` | `test_ingest.py:472` | itself |

Both existing tests use hand-built `Segment` values and a stub producer, and stay valid — the
adapter is simply a third implementation of the same protocol. No change needed.

## `Segment` — `diarization.py:55` (**unchanged**, new construction site)

Widely referenced across `diarization.py`, `diarization_acceptance.py`, `reframe.py`,
`pipeline.py` and their tests. The adapter only constructs it. The constructor already enforces
exact-int ms and `end > start`, which is what makes AC-5/AC-6 enforceable rather than advisory.

## `run_pipeline` — `pipeline.py:1243` (**unchanged**; `diarizer=` already exists at line 1259)

No signature change. The parameter has been there since D-240 and has never had a caller passing
a real producer.

## Gap found

`durable.py` and `durable_workflow.py` arrived in the merge (`aaa5971`) and reach
`build_parser`/`_build_and_run`. Their only coverage of the producer wiring is the single
direct-vs-durable equivalence test above. That is adequate for this change — it compares whole
`PipelineRun`s — but it is one test guarding two entry points, and worth knowing.
