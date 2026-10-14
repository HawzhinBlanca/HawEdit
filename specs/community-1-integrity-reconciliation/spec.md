# Community-1 EARS

WHEN pinned authenticated metadata differs, THE fetcher SHALL refuse provisioning.
WHEN exact hashes are available, THE integrity row SHALL preserve their provenance
and the existing revision, sizes, file-set and digest-verification requirements.
WHEN an existing downloader environment is unaudited, THE system SHALL refuse it
without installing packages or overriding its profile.
WHEN provisioned bytes differ or publication is uncertain, THE model store SHALL
refuse readiness and preserve existing assets.

Regression mapping: test_integrity_manifest_cannot_drift_from_the_provisioning_revision;
test_gated_checkpoint_with_redacted_digests_is_refused_not_approximated;
test_download_client_is_exact_and_never_auto_installed;
test_download_client_refuses_transitive_profile_drift_before_import;
test_happy_download_verifies_then_publishes_without_a_partial_final;
test_final_published_path_is_reverified_and_invalid_bytes_are_preserved.
These are existing automated controls, not evidence of current real provisioning.
Any regression relying on the old checked-in blocked state needs an approved
strict test-contract extension, preserving redacted-metadata refusal and adding
actual pinned verified-provisioning coverage. Do not weaken or silently change it.
