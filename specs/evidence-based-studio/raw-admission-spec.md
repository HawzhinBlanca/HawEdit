# Raw Journal EARS

RA1: WHEN a journal has unknown schema objects or migration version, THE inspector SHALL
refuse before interpreting records. Tests: test_raw_schema_drift_refuses,
test_raw_migration_drift_refuses, test_actual_pinned_schema_accepts.
RA2: WHEN rows exceed count, encoded text bytes, field or query limits, THE inspector SHALL
refuse without truncation or JSON decoding. Tests: test_raw_limits_refuse_before_json,
test_raw_field_type_and_size_refuse, test_raw_deadline_refuses, test_raw_invalid_limits_refuse.
RA3: WHEN any workflow lacks matching outbox identity or host policy, THE inspector SHALL
refuse all admission including terminal jobs. Tests: test_raw_workflow_policy_refuses,
test_raw_missing_outbox_refuses, test_raw_confirmed_job_is_included.
RA4: WHEN a serialization tag, JSON document or ID-only shape is unsafe, THE inspector SHALL
refuse without DBOS deserialization. Tests: test_raw_workflow_payload_refuses,
test_raw_step_payload_refuses, test_raw_pickle_never_executes.
RA5: WHEN unsupported persisted surfaces or queue policies exist, THE inspector SHALL refuse.
Tests: test_raw_unsupported_surfaces_refuse, test_raw_queue_policy_refuses.
RA6: WHEN admission succeeds or refuses, THE inspector SHALL preserve the original database,
outbox and private namespace. Tests: test_actual_pinned_schema_accepts,
test_raw_read_only_preserves, test_raw_lost_binding_refuses_without_recreation.

RA7: WHEN execution state conflicts with its result/error, THE inspector SHALL refuse;
genuine absent ORM attributes and canonical execution UUIDs SHALL remain descriptive data.
Tests: test_raw_state_payload_conflict_refuses, test_actual_inert_dbos_output_is_admitted,
test_raw_absent_orm_attributes_accept_without_authority,
test_raw_terminal_null_queue_accepts_without_recovery, test_raw_portable_error_accepts_without_replay.

All criteria remain WIP until exact gate and applicable same-SHA CI; helpers cannot enable jobs.
