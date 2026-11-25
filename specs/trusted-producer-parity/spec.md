# EARS Acceptance Criteria

TP1: WHEN trusted host configuration selects existing governance/location values,
THE studio SHALL forward validated exact values through the shared parser and
bind them to persisted job content and execution reconstruction.
Tests: test_trusted_governance_reaches_shared_parser,
test_trusted_governance_is_bound_and_rehydrated,
test_trusted_governance_drift_refuses_recovery.

TP2: WHEN host values are malformed or incompatible with the actual route,
THE studio SHALL refuse before model work or egress without a fallback.
Tests: test_invalid_trusted_governance_is_refused,
test_invalid_trusted_governance_text_is_refused,
test_confidential_developer_route_never_becomes_vertex,
test_confidential_vertex_requires_existing_governance,
test_developer_route_refuses_vertex_location.

TP3: WHEN a browser supplies host governance/provider/location/authority fields,
THE request boundary SHALL refuse rather than treat them as an owner grant.
Test: test_browser_cannot_select_trusted_governance.

TP4: WHEN existing default callers run, THE studio SHALL preserve effective
parser behavior, exact default argv, original positional fields and producer
routing, with no new public option or spending/publication permission.
Test: test_default_producer_parser_parity; existing affected whole modules.

These automated criteria do not authenticate owner statements or prove real
Vertex retention, rights, billing, neural quality, publication or acceptance.
