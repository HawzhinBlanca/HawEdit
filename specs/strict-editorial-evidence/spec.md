# Specification — strict persisted editorial evidence

## AC-1 — exact JSON document

WHEN `--verdict` reads persisted Stage 4 evidence, THE pipeline SHALL read only a bounded byte
budget and SHALL reject duplicate keys, non-standard numeric constants, excessive nesting, a
non-object document, missing required members, and unknown members before constructing a verdict.

Evidence: `test_persisted_verdict_json_is_an_exact_document`,
`test_cli_refuses_ambiguous_persisted_verdict_json_without_a_traceback`,
`test_cli_bounds_persisted_verdict_before_parsing_or_media_work`.

## AC-2 — exact scalar types

WHEN a verdict, editorial block, boundary, output block, rejection, or clip is deserialized, THE
system SHALL reject booleans used as integers or scores, non-finite numbers, coercible strings, and
wrong container types.

Evidence: `test_boundary_json_refuses_non_schema_numbers`,
`test_section_5_json_refuses_bool_as_number`,
`test_persisted_verdict_refuses_non_schema_numbers`.

## AC-3 — exact object members with legacy compatibility

WHEN a §5 block is deserialized, THE system SHALL reject unknown object members while continuing to
read the explicitly documented legacy omissions and SHALL reject a nested block whose JSON
container is not an object or null as applicable.

Evidence: `test_section_5_json_refuses_unknown_members`,
`test_section_5_nested_blocks_require_objects`, existing legacy round-trip tests.

## AC-4 — independent render invariant

WHEN a boundary has valid JSON scalar types but violates sentence containment, THE boundary SHALL
remain constructible and `assert_boundary_invariant` SHALL still refuse it before render.

Evidence: existing `test_a_clip_whose_boundary_violates_the_invariant_is_not_renderable` and
`test_boundary_shape_validation_does_not_replace_the_render_gate`.
