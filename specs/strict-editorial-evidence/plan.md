# Plan — strict persisted editorial evidence

Approved-by: Hawa — 2026-08-17 (inherited from the explicit autonomy-first true-10/10 plan)

1. Add discriminating failures for booleans-as-numbers, non-finite values, wrong containers,
   duplicate keys, unknown fields, and a traceback-free CLI refusal.
2. Add strict non-coercing scalar/object helpers at the existing boundary-contract seam.
3. Harden each §5 `from_dict` path while preserving named legacy omissions and the independent
   render invariant.
4. Add `JudgeVerdict.from_json` and route `--verdict` through it.
5. Run focused and adjacent suites, refresh the source-bound VEX policy, run the canonical clean
   gate, commit explicit paths, push, and require exact-SHA hosted checks.

Exit: persisted editorial evidence has one unambiguous JSON meaning and cannot turn JSON booleans,
non-finite constants, ignored fields, or container coercions into renderable client metadata.
