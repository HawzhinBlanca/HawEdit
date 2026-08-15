# Specification — credential validation response bounds

Parent: true-10/10 AC-10 and AC-12.

1. WHEN the credential-validation transport receives a response, THE transport SHALL read no more
   than a fixed byte ceiling plus one detection byte and SHALL return a bounded refusal for an
   oversized response.
2. WHEN a provider or network diagnostic contains control characters or excessive text, THE
   credential validator SHALL return one printable single-line detail under a fixed character
   ceiling.
3. WHEN a provider diagnostic contains the submitted credential, THE credential validator SHALL
   redact it before the detail can reach a caller or CLI stream.
4. WHEN an ordinary short provider message is returned, THE validator SHALL preserve its useful
   wording.

Evidence tests:

- `test_key_validation_bounds_and_redacts_an_untrusted_provider_error`
- `test_key_validation_bounds_an_untrusted_network_error`
- `test_the_live_key_probe_refuses_an_oversized_response_without_reading_it_all`

