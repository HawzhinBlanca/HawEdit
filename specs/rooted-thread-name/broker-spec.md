# Bounded Broker EARS

| Criterion | Named Regression |
| --- | --- |
| WHEN original libc fopen requests a registered original thread comm, THE broker SHALL copy the bounded request and inject the genuine anchored comm description atomically. | test_thread_broker_actual_fopen_and_atomic_injection |
| WHEN a notification names a foreign/unregistered target, THE broker SHALL return real EPERM without injecting any descriptor. | test_thread_broker_foreign_target_refuses |
| WHEN no notification arrives, THE broker SHALL interrupt the actual kernel receive within its deadline and retain refusal rather than hang. | test_thread_broker_idle_receive_has_real_deadline |
| WHEN the original listener slot is substituted, THE broker SHALL refuse and SHALL NOT close that foreign slot. | test_thread_broker_listener_substitution_preserves_foreign_slot |
| WHEN the caller supplies a non-listener description, THE broker SHALL refuse before any worker resumption or descriptor injection. | test_thread_broker_non_listener_refuses |
| WHEN a supplied deadline is invalid, THE broker SHALL refuse before kernel or signal side effects. | test_thread_broker_invalid_deadline |
| WHEN an original notification has different flags/mode/dirfd or a noncanonical task path, THE broker SHALL return real EPERM and SHALL NOT inject a descriptor. | test_thread_broker_exact_open_shape_refuses |
| WHEN an original default one-shot alarm already exists, THE broker SHALL use the earlier deadline and restore only its remaining time without extending it. | test_thread_broker_preserves_original_timer_without_extending_it |
| WHEN a custom controller watchdog owns SIGALRM, THE broker SHALL refuse without replacing that handler. | test_thread_broker_refuses_foreign_watchdog_handler |
| WHEN the original one-shot alarm expires before the broker deadline, THE broker SHALL interrupt at that earlier original deadline. | test_thread_broker_respects_earlier_original_deadline |
| WHEN a periodic controller timer exists, THE broker SHALL refuse without resetting it. | test_thread_broker_does_not_replace_periodic_timer |

Whole original registry/isolated snapshot/GPU/entropy/owner/control/claims cohorts
and exact full committed gate are required. Current independent VEX and same-SHA
CI remain separate. No row promotion from component tests or diagnostic success.
