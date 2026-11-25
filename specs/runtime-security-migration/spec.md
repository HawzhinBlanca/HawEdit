# EARS Requirements

| ID | Requirement | Named automated regression |
|---|---|---|
| RM1 | WHEN WSL dependencies are installed, THE runtime SHALL bind urllib3 2.8.0 and Werkzeug 3.1.9 to independently verified upstream wheel hashes. | test_wsl_http_security_patches_bind_exact_upstream_wheels |
| RM2 | WHEN these utility pins change, THE runtime SHALL preserve every other existing requirement byte. | test_http_security_patch_preserves_other_runtime_requirements |
| RM3 | WHEN the patched runtime is provisioned, THE generation identity SHALL differ from the original generation without rewriting its receipt or environment. | test_http_security_patch_uses_a_distinct_environment_generation |
| RM4 | WHEN current source differs from qualified security evidence, THE security gate SHALL refuse admission rather than infer approval from installation. | test_checked_in_policy_binds_current_lock_and_assets_and_closes_report (existing, expected unresolved refusal) |

Real installation, hostile-input behavior, actual neural equivalence and rollback
need separate immutable evidence; lock-only regressions do not prove them.
RM4 maps the existing current-policy obligation; do not weaken it to make it pass.

## Checkpoint Metadata Extension

- SH1: WHEN a shard map names an absolute, traversing or Windows-special path,
  THE pre-load guard SHALL refuse before a model loader opens any shard.
  Tests: test_model_shard_unsafe_paths_are_refused.
- SH2: WHEN an index or shard is nonregular, linked or missing, THE pre-load guard
  SHALL refuse without following it or blocking on a special file.
  Tests: test_model_shard_nonregular_members_are_refused,
  test_model_shard_hardlinked_members_are_refused,
  test_model_shard_parent_link_is_refused, test_model_shard_missing_member_is_refused.
- SH3: WHEN an index is malformed, ambiguous or exceeds1MiB, THE pre-load guard
  SHALL refuse boundedly before model-stack parsing.
  Tests: test_model_shard_invalid_indexes_are_refused, test_model_shard_invalid_json_is_refused,
  test_model_shard_duplicate_keys_are_refused, test_model_shard_oversized_index_is_refused,
  test_model_shard_nonfinite_json_is_refused.
- SH4: WHEN an index lists contained regular sibling/nested shards or a checkpoint
  has no index, THE existing guard SHALL preserve compatible loading behavior.
  Tests: test_model_shard_valid_indexes_are_accepted, test_builtin_transformers_implementations_are_accepted.
