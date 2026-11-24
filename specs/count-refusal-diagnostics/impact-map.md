# Caller Impact

Actual3-pair map in research.md. Changed symbol only GuardedGeminiTransport/_call,
called by its serialized __call__. _send serves direct count, generation's internal
count and post-intent generation; only the internal-count exception handler changes.
Preserve original ExternalReconciliationError; native StudioStorageError remains
the typed cause of a journal-specific ExternalReconciliationError. Do not
change actual _send checks, response validation, reservations/replay, or generation
uncertainty. Other transport exceptions retain the provider-unavailable wrapper.

Runtime callable references are not returned by LSP for __call__; real existing
callers include SignedStudioTransport's journal and explicit injected judge
transports in tests/test_studio_billing.py. Earlier current21-pair map records
signed transport/billing/parser builder callers. Whole billing/authorization/
gemini and workflow-recovery suites protect public/error contracts. New named
regressions exercise real wall-clock expiry, native SQLite schema corruption and
an actual local HTTP count disconnect, never a mocked guard or weakened test.
The existing failing expiry test is unchanged, including its expired assertion.

First broader run caught two established post-count storage callers requiring
ExternalReconciliationError: database replacement and journal drift during count.
Keep both existing assertions unchanged; preserve this public contract with an
explicit journal diagnostic/native cause. Before correcting production and the
new regression, actual2-pair Serena map found _call/new storage test, unchanged
source; raw count-contract-correction-map-20261008/serena-map.json. The new test
adds typed-cause/schema assertions, not a relaxed refusal or repaired journal.
