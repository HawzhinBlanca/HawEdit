# Confidential judge routing was an unheld copy

> Integrated 2026-08-10 from protected-main finding `b24ce15` against the readiness Gemini
> transport and credential hardening.

`GeminiJudge.__init__` and `VertexGeminiJudge.__init__` each call §7's `route(self)`. The Vertex
class intentionally does not call `super().__init__`: it uses ADC instead of a Gemini API key.
That makes the routing guard a second constructor call site, not inherited behavior.

The previous shadow-model test instantiated only `GeminiJudge`. Removing the Vertex call therefore
left the suite green upstream and allowed the confidential Vertex endpoint to be constructed for
`gemini-3.1-pro`, the evaluated-but-not-routable shadow. The guard itself was correct; its copied
wiring was not held.

The readiness suite now declares the complete constructor map for `GeminiJudge` and all transitive
subclasses. It verifies three properties:

- the declared constructor names equal the production class hierarchy in both directions;
- every constructor refuses `JUDGE_SHADOW` with `NotRoutable`;
- every constructor accepts the pinned `KURDISH_EDITORIAL_JUDGE` and puts that model in its URL.

The positive control matters: a constructor that rejected every model would otherwise satisfy the
shadow test. The hierarchy equality matters: adding another confidential route cannot silently
escape the matrix.

Focused result: `tests/test_gemini.py` passes 65/65, including five new generated cases covering
both developer API and Vertex constructors.
