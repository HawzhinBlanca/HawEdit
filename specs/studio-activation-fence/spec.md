# EARS

SF1: WHEN a protected callback enters while its genuine owned host is starting,
THE runtime SHALL wait only within a validated finite bound and return only after
the actual active runtime/registry/engine/lease verification succeeds.
test_activation_wait_handles_actual_pending_recovery;
test_activation_wait_verifies_actual_runtime_before_return.

SF2: WHEN startup fails, drain/close begins, timeout expires or runtime identity
changes, THE wait SHALL refuse without consumer work or forced lease release.
test_activation_wait_refuses_failed_startup;
test_activation_wait_refuses_draining_and_closed;
test_activation_wait_refuses_runtime_drift;
test_activation_wait_timeout_is_bounded.

SF3: WHEN invalid/unbounded waits are supplied or the launching main thread waits
during startup, THE runtime SHALL refuse instead of blocking startup.
test_activation_wait_rejects_invalid_timeout;
test_activation_wait_does_not_deadlock_launch_thread;
test_activation_wait_refuses_unlaunched_runtime.

SF4: WHEN existing callers use verify/launch/close, THE runtime SHALL preserve
their refusal, registry ownership, private storage and live-worker lease retention.
test_activation_signal_is_not_authority; whole tests/test_studio_runtime.py.
This is synchronization, not model, spending, billing or publication authority.
