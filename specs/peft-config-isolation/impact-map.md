# Impact Map

Actual Serena map: peft-config-map-765b502-20261007/serena-map.json under
C:/Users/Wareen/AppData/Local/HawEditEvidence. Source unchanged during mapping.

| Symbol | Callers / impact | Verification |
| --- | --- | --- |
| OmniAsrBackend._load_adapted_llm | _load; held-consumer assembly regression | complete test_champion_held_assets.py; real saved tensors and decoded ZAR window |
| OmniAsrBackend._load | transcribe_segment; held/identity/lifecycle tests | complete test_asr.py, test_adapter_identity.py, test_asr_model_lifecycle.py |
| Dynamic producer / worker backend dispatch | native producer; checkpoint worker; admission, context, resume and fail-stop paths | complete test_asr_resume.py, test_asr_stop.py, test_asr_completion.py, test_asr_context.py, test_asr_admission_cache.py, test_asr_worker_diagnostics.py |
| Canonical asset/config boundary | held descriptors, direct cards, metadata, claims | complete test_omni_assets.py, test_claims.py; exact full gate |

No public signature changes. Only instance ownership of the same PEFT config.
Keep Fairseq2 Linear feature aliases, base recipe, vocabulary derivation,
dtype/device, decoder, journal policy, CTC and release handoff unchanged.
External composition doubles do not establish actual weight loading or accuracy.
