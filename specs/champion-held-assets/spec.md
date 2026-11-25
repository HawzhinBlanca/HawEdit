# EARS Specification

1. WHEN the champion loads, THE backend SHALL verify canonical assets before pipeline
   imports and consume base/CTC/tokenizer through held verified aliases.
   Tests: test_champion_verifies_canonical_assets_before_import,
   test_omni_loader_reads_only_held_verified_descriptors.
2. WHEN a bundle is fingerprinted, THE identity SHALL retain its existing full schema-2
   digest and input guards. Tests: test_adapter_identity_is_full_versioned_three_file_digest,
   test_adapter_identity_refuses_unsafe_or_ambiguous_inputs.
3. WHEN verified bundle consumers run, THE boundary SHALL retain all three input
   descriptors, expose only those inputs, and refuse original input or directory drift
   before returning a cached pipeline. Tests: test_open_adapter_bundle_retains_and_closes_inputs,
   test_open_adapter_bundle_refuses_mutation_during_consumption,
   test_verified_adapter_aliases_bind_replaced_paths.
4. WHEN descriptor aliases are unavailable, THE champion loader SHALL refuse with an
   actionable runtime error instead of reopening original paths.
   Test: test_verified_adapter_aliases_bind_replaced_paths (native unsupported branch).
5. WHEN construction raises, THE boundary SHALL close descriptors and remove only its
   own temporary aliases without mutating the original bundle.
   Test: test_verified_adapter_cleanup_on_consumer_failure.
6. WHEN a champion pipeline is constructed, THE loader SHALL retain D-181's trainer
   recipe and unadapted CTC timing model. Test: test_champion_consumers_receive_held_assets;
   additionally real WSL model/decoded-development-audio evidence, not synthetic inference.

These criteria do not claim CER, meaning fidelity, throughput acceptance, qualified
security review, completed delivery or AC-1-AC-12 release acceptance.
