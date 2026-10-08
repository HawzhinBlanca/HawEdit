# EARS

WHEN a private host evidence directory has a canonical alias, THE host SHALL
require repeated original/canonical private identity and access parity.
test_host_evidence_canonical_directory_preserves_private_identity.

WHEN a repeated directory expectation selects foreign private storage, THE host
SHALL refuse and preserve both namespaces.
test_host_evidence_canonicalization_refuses_foreign_expectation.

WHEN canonical evidence preflight runs, THE preflight SHALL not create evidence.
test_host_evidence_canonical_preflight_does_not_mint_evidence.

WHEN evidence exists, THE preflight SHALL refuse overwrite and preserve bytes.
test_host_evidence_canonical_preflight_preserves_existing_evidence.

WHEN original storage disappears or is replaced, THE host SHALL refuse adoption.
test_host_evidence_canonicalization_refuses_missing_original;
test_host_evidence_canonicalization_refuses_replaced_original.

WHEN scoped canonical evidence matches source, policy and artifact bytes, THE
binding recheck SHALL accept that binding without granting execution authority.
test_host_evidence_binding_accepts_actual_canonical_private_parent.

WHEN an artifact has a foreign parent or changed bytes, THE binding recheck
SHALL refuse and preserve the original evidence.
test_host_evidence_binding_refuses_foreign_private_parent;
test_host_evidence_binding_refuses_changed_bytes.
