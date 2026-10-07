# EARS Specification

1. WHEN a persisted ID-only job is prepared, THE boundary SHALL reconstruct the
   original studio configuration through the shared request/parser/builder and
   preserve source and immutable request identity.
   Tests: test_execution_input_preserves_shared_configuration,
   test_execution_input_survives_store_reconstruction.
2. WHEN saved arguments differ from the supported reconstructed request, THE
   boundary SHALL refuse them before creating work artifacts.
   Test: test_execution_input_refuses_unbound_arguments.
3. WHEN source bytes, effective configuration, current source package, expected
   workflow or host execution binding differ, THE boundary SHALL refuse execution
   inputs and preserve the original submission/upload records.
   Tests: test_execution_input_refuses_configuration_drift,
   test_execution_input_refuses_changed_source,
   test_execution_input_refuses_wrong_host_binding.
4. WHEN private storage is unavailable or substituted, THE boundary SHALL refuse
   without inventing state or recreating missing journals.
   Tests: test_execution_input_refuses_lost_outbox,
   test_execution_input_refuses_unsafe_work_directory.
5. WHEN an input record is returned, THE boundary SHALL expose no client-token,
   publication or approval claim, and its work directory SHALL be job-scoped and
   owner-private.
   Test: test_execution_input_preserves_shared_configuration.

No input-only record is authorization to run models, bill a provider or publish.
