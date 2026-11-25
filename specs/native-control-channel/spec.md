# EARS

WHEN control mode is absent/false, THE executor SHALL preserve exact binary EOF
behavior. test_native_control_false_preserves_binary_eof plus whole existing IO.

WHEN control options are not exact bool/finite positive bounded numbers, THE
executor SHALL refuse before launch. test_native_control_invalid_mode_never_launches;
test_native_control_invalid_exchange_deadline_never_launches.

WHEN control is enabled, THE executor SHALL frame immutable request bytes and
keep original stdin until valid terminal. test_native_control_binary_request.

WHEN challenges fragment/repeat or malformed/unsolicited/trailing frames arrive,
THE executor SHALL reply exactly to complete original fresh frames or refuse.
test_native_control_fragmented_challenge; test_native_control_multiple_exchanges;
test_native_control_malformed_exchange_refuses.

WHEN an exchange stalls, THE executor SHALL enforce its finite exchange and
overall deadlines using original-scope cleanup. test_native_control_stalled_supervisor;
test_native_control_nonreader_deadline; test_native_control_exchange_deadline.

WHEN either stream exceeds the combined ceiling, THE executor SHALL count control
bytes too and refuse. test_native_control_shared_output_limit.

WHEN stdout ends without terminal, THE executor SHALL refuse. test_native_control_missing_terminal.

WHEN terminal arrives but original scope remains live, THE executor SHALL not
return success. test_native_control_terminal_not_scope_completion.

WHEN distinct exchanges reach the explicit65536 nonce budget, THE framing parser
SHALL refuse further frames. test_native_control_parser_nonce_budget (synthetic
state-unit test, not independent native/Linux/model execution evidence).

All native IO cleanup, original member death and arena uncertainty assertions
remain intact. This transport does not establish Linux/GPU/provider drain,
durable attempt release, authenticated review/export or reel publishability.
