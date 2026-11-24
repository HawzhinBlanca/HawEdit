# EARS

WHEN original native release is refused, THE owner SHALL retain the exact
unreleased capability and remaining image access, mark uncertainty and not closed.
test_native_release_failure_preserves_original_capabilities[_job,_process,_thread,_observed-close].

WHEN member observation release fails during stop, THE owner SHALL still request
termination through its original job and preserve unreleased capabilities without
an active stale-snapshot finalizer.
test_native_release_failure_preserves_original_capabilities[_observed-stop,_observed-close].

WHEN a physical fault is removed, THE uncertain owner SHALL refuse automatic
close retry and new scope admission; mere physical recovery is not reconciliation.
All five parameter cases above include these additional refusal checks.

WHEN ordinary Python references are collected, THE uncertain owner SHALL retain
the exact original native capability without snapshot finalization releasing it.
All five cases observe the original handle after GC.

WHEN healthy cleanup succeeds, THE owner SHALL preserve original scope quiescence
and idempotent closed behavior. Complete test_native_process/test_native_io suites,
including test_native_owner_context_exit_drains_actual_running_descendants.

No criterion treats these native observations as Linux/GPU/provider, billing,
creator-study, editorial-quality, authenticated review or publication evidence.
