# EARS Specification

- WHEN the host, bounds, utility bytes or FD-exec capabilities are unavailable,
  THE bootstrap SHALL refuse before launch. test_linux_bootstrap_unsupported_host;
  test_linux_bootstrap_invalid_bounds; test_linux_bootstrap_bad_utility_refuses.
- WHEN the creator starts with any standard stream closed, THE bootstrap SHALL
  refuse before allocating its ownership descriptors or changing other streams.
  test_linux_bootstrap_closed_creator_stream_refuses_before_allocation.
- WHEN utility admission succeeds, THE bootstrap SHALL retain immutable hashed
  executable bytes and original owner description anchors.
  test_linux_bootstrap_sealed_utility_refuses_mutations.
- WHEN the creator or descriptors differ, THE bootstrap SHALL refuse without
  closing substituted foreign resources. test_linux_bootstrap_foreign_descriptor;
  test_linux_bootstrap_parent_cannot_exec.
- WHEN original owner death precedes handler installation, THE bootstrap SHALL
  refuse against that original identity before any exec.
  test_linux_bootstrap_owner_dead_before_exec_refuses.
- WHEN the direct creator child executes, THE bootstrap SHALL isolate inherited
  control FDs and consume the retained sealed utility with fixed namespace flags.
  test_linux_bootstrap_original_scope_owner_death.
- WHEN original owner exits normally or is killed, THE bootstrap chain SHALL
  terminate original namespace-init and its original setsid member.
  test_linux_bootstrap_original_scope_owner_death.

These are required tests, not passing evidence. Byte sealing of one utility does
not admit all model/runtime/source/input bytes, GPU/provider/billing reconciliation,
durable attempt completion or publication. The full approved goal is unchanged.
