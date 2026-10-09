# EARS Specification

- WHEN the host, kernel query or libc capability is unavailable, THE scope SHALL
  refuse before admission. test_linux_scope_unsupported_host_refuses.
- WHEN bounds or a channel are invalid, THE scope SHALL refuse without sending
  a worker release. test_linux_scope_invalid_bounds_refuse.
- WHEN handoff framing, nonce, credentials, counts, descriptor types or original
  namespace relationships differ, THE scope SHALL refuse and preserve uncertainty.
  test_linux_scope_invalid_handoff_refuses.
- WHEN the sender does not seal descriptor transfer with actual write-shutdown
  and EOF, THE scope SHALL refuse; an empty packet is not shutdown.
  test_linux_scope_empty_packet_does_not_seal_handoff.
- WHEN admitted, THE scope SHALL retain original non-inherited namespace/init/
  member descriptors with description anchors and creator ownership before any
  caller release. test_linux_scope_retains_original_descriptors.
- WHEN an original descriptor is substituted or creator differs, THE scope SHALL
  refuse without signaling/closing substituted foreign resources.
  test_linux_scope_substitution_retains_uncertainty;
  test_linux_scope_foreign_creator_refuses.
- WHEN stop is requested, THE scope SHALL signal only the admitted original init
  pidfd and observe every retained member under an absolute finite deadline.
  test_linux_scope_stop_observes_original_detached_member.
- WHEN stop/observation/cleanup is uncertain, THE scope SHALL retain exclusion
  and remaining original capabilities, refuse new admission and never report
  publication or release an attempt. test_linux_scope_uncertainty_refuses_reentry.

These criteria do not define full producer admission, owner-death bootstrap,
namespace reentry calibration, GPU/provider/billing drain or media quality.
Those remain requirements of the full approved plan, not waived criteria.
