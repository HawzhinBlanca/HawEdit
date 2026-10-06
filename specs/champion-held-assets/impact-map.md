# Caller Impact

Actual Serena map and baseline hashes are in research.md.

| Symbol | Observed callers | Protection |
| --- | --- | --- |
| adapter_fingerprint | OmniAsrBackend.adapter_name; WslOmniAsrProducer.model_identity; create_omni_asr_producer; tests/test_adapter_identity.py and tests/test_asr.py | Same signature and schema-2 digest; complete affected tests |
| OmniAsrBackend._load | transcribe_segment; align_segment; cached identity, stock integrity and held consumer tests | Both branches use held canonical assets; publish cache only after guards exit successfully |
| OmniAsrBackend._load_adapted_llm | _load only in LSP map | Private required checkpoint_uri argument; alias tokenizer URI, no resolved original path; real champion construction |
| open_verified_omni_assets | _load, import/export surface | Reused unchanged for adapted and stock routes |
| assert_effective_omni_cards | _load; models._probe_local_omni_runtime; card tests | Reused unchanged before adapted construction |

Indirect paths: asr_worker.run_request constructs the default champion backend;
pipeline/build configuration selects WslOmniAsrProducer. Source-bound WSL runtime
receipts and operation journals must be regenerated/revalidated, never admitted as
compatible solely because output is expected unchanged. Prior raw transcripts stay
historical evidence. Existing default/explicit-stock selection semantics remain.

Supplemental map at 2e44930 confirms `_load_adapted_llm` callers are `_load` and
`test_champion_consumers_receive_held_assets`. No public signature change for the
direct-card correction. Extend the latter to reject global name lookup while
retaining all existing architecture/vocabulary/registration assertions.
