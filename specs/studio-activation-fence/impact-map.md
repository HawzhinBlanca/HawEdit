# Caller Impact

Actual Serena pairs in research.md; lifecycle source found before edits.
Constructor/launch/verify have no static references returned: actual existing
callers are embedded native subprocess programs in tests/test_studio_runtime.py,
which the language server cannot resolve as Python calls. close is also called
by launch's failure path. _main_thread serves launch/close; _verify_owner serves
launch/verify/close and the owned engine callback. Neither helper is changed.

Changed constructor: add one private event, preserve all storage/identity fields.
Changed launch: signal only after genuine engine/registry checks and active state.
Changed close: signal after entering draining, before joining live workers.
New await_activation: validate finite bounds; wait only while starting, never on
the launching thread; always invoke unchanged verify before return. No callers
adopt the actual producer/HTTP path in this unit.

New named tests cover genuine private lifecycle/subprocess/recovery with DBOS2.29.0,
injected startup failure, timeout, actual runtime drift, draining/closed refusal,
and invalid bounds. Whole existing runtime, admission, queue, attempt, submission,
execution-input, generation and intake suites protect affected contracts. Events
never replace actual engine, native lease, registry, PID or owner authority.

Before correcting new regression setup, actual4-pair Serena map found _CHILD,
_run, pending-recovery and runtime-drift tests, source unchanged. _CHILD is used
only by _run; _run serves this module's lifecycle tests. No production callers.
Raw studio-activation-test-correction-map-20261008/serena-map.json. Actual DBOS
effective max_executor_threads lives in runtimeConfig, not an unused outer key.
The observational recovery-start wait uses8s, matching the prior real experiment;
the activation timeout assertion and positive/negative acceptance are unchanged.
