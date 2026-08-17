# Specification — credential header preflight

Parent: true-10/10 AC-10 and AC-12.

1. WHEN a submitted key is empty, excessive, non-ASCII, contains whitespace, or contains an HTTP
   control character, THE validator SHALL return a generic refusal before constructing a request or
   invoking any transport.
2. WHEN a malformed key is refused, THE refusal and CLI streams SHALL NOT contain the submitted
   value or a traceback.
3. WHEN a bounded printable ASCII value is submitted, THE validator SHALL continue to use Google's
   live response—not a local shape regex—as the validity decision.

Evidence tests:

- `test_header_unsafe_keys_are_refused_before_transport`
- `test_the_panel_refuses_a_header_unsafe_key_without_printing_it`
- existing accepted/rejected live-transport controls in `tests/test_credentials.py`

