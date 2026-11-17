# EARS

WHEN deadlines or host/STD resources are invalid, THE endpoint SHALL refuse
before adopting control IO. test_linux_owner_invalid_deadline;
test_linux_owner_current_host_boundary; test_linux_owner_regular_stdio_refuses.
Named FIFOs are refused: test_linux_owner_named_pipe_refuses.

WHEN a request is fragmented/binary, THE endpoint SHALL return its exact bounded
immutable payload once. test_linux_owner_native_interoperability;
test_linux_owner_fragmented_request.

WHEN request framing is malformed/truncated/oversized, THE endpoint SHALL refuse
without generating a terminal frame. test_linux_owner_invalid_request.

WHEN it challenges the owner, THE endpoint SHALL generate a fresh16byte nonce,
fully write it and consume an exact HER1 response before another exchange.
test_linux_owner_real_exchanges; test_linux_owner_bad_reply;
test_linux_owner_replayed_reply.

WHEN an input/output or exchange stalls, THE endpoint SHALL refuse within finite
exchange AND overall budgets, without blocking buffered IO or background writers.
test_linux_owner_stalled_request; test_linux_owner_stalled_reply;
test_linux_owner_nonreading_owner; test_linux_owner_overall_deadline.

WHEN called out of order/after refusal or by a foreign process/thread, THE
endpoint SHALL refuse without adopting another request/session.
test_linux_owner_invalid_order; test_linux_owner_single_lifetime;
test_linux_owner_foreign_thread; test_linux_owner_foreign_process.
Numeric thread-ID reuse is not ownership: test_linux_owner_recycled_thread_id_refuses.
Unsolicited bytes and sticky refusal: test_linux_owner_unsolicited_reply;
test_linux_owner_refusal_sticky.

WHEN finishing after an exchange, THE endpoint SHALL emit only HED1 then observe
original owner EOF, rejecting premature/trailing bytes.
test_linux_owner_terminal_requires_owner_eof; test_linux_owner_terminal_trailing_reply.

WHEN closing normally, THE endpoint SHALL close only its verified original
non-inherited duplicates and restore shared original blocking flags; closing
SHALL NOT emit terminal or imply scope/attempt completion.
test_linux_owner_owned_descriptor_cleanup; test_linux_owner_close_not_terminal.
Preserve initially nonblocking STD: test_linux_owner_preexisting_nonblocking_restored.

WHEN an owned descriptor is substituted or cleanup uncertain, THE endpoint
SHALL preserve refusal and refuse automatic retry/new admission without closing
the foreign replacement. test_linux_owner_substituted_descriptor_retained.
Same-inode reopen is not an original description:
test_linux_owner_same_inode_reopen_retained.

Every criterion is protocol/descriptor scoped. Linux/GPU/provider quiescence,
model/source/security admission, durable attempt release and publication require
their own original evidence; no ready/completed/clear flags are added.

WHEN unit evidence is added, THE documentation SHALL retain a valid header
naming its real commit, media applicability, host and commands.
test_new_evidence_names_its_commit_media_and_host.

WHEN a source module is added, THE README SHALL map that module's actual scope
without asserting unimplemented production callers.
test_the_module_map_covers_every_module.
