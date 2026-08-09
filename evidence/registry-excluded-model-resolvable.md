# §7 could both register and exclude a model, and the excluded one won

> Measured 2026-08-09 on hawapc01 against `3fb2d75`, against a **green** 1,119 baseline.

`resolve` reads `REGISTRY` before `EXCLUDED`:

```python
entry = REGISTRY.get(model_id)
if entry is not None:
    return entry
excluded = EXCLUDED.get(model_id)
if excluded is not None:
    raise ModelExcluded(...)
```

So a model id in both tables resolves — the contradiction settles **in favour of the excluded
model**. Nothing asserted the tables were disjoint, and nothing related them to each other:
`test_exclusions_match_section_7_exactly` compares the *cells* `EXCLUDED` self-declares against
§7's exclusion column, which stays correct when an excluded id is also registered.

Two of §7's nine exclusions are `CC-BY-NC-4.0` hard rejects —
`mms-300m-1130-forced-aligner` and `RevgeAI/vekol-stt-ckb-small` — so the same hole can route work
to a NonCommercial model. (The other seven are architectural: CLIP for frame-averaging, Whisper
because "OmniASR is stronger for ckb", and so on.)

## The measurement, and three attempts to get it right

`Whisper` added to `_ENTRIES` with a `blueprint_model_cell` §7 already contains, **no role**, and
`MIT` (attribution not required):

```
  in EXCLUDED: True | in REGISTRY: True
  resolve() -> RETURNED 'Normalization' — NO ModelExcluded

  pytest tests/ -q   ->  exit=0,  0 FAILED
```

**My first two attempts said CAUGHT and both were wrong.** They are worth recording because each
failed the same way, in the opposite direction to the usual mutation error:

1. I appended a `REGISTRY = MappingProxyType(dict(REGISTRY) | {...})` redefinition to the end of
   the module. 4 failures — but they were `test_the_gpu_modules_typecheck_with_the_gpu_extra_absent`
   and three `test_gate.py` subprocess tests. The mutation was *malformed code*, caught by the
   typechecker, and nothing to do with exclusions.
2. I inserted a proper entry inside `_ENTRIES` but gave it `CC_BY_SA_4_0`. 2 failures — both
   `test_claims.py` attribution tests, because the README's attribution list is generated from the
   registry and that licence requires attribution.

Only the third, minimal mutation isolates the behaviour. **A mutation caught for the wrong reason
reads as protection that is not there**, which is the mirror image of D-079's lesson — there, a
mutation *surviving* for the wrong reason (a redundant sibling) read as exposure that was not
there.

This also settles a disagreement with the second adversarial pass, which reported this and whose
baseline was **red** (a worktree has no `.venv`, so `test_gate.py` contributes 9 failures). Its
conclusion was right; its method could not have distinguished the three cases above, because
comparing failure *counts* against a red baseline hides which tests failed and why.

## The fix, and why it is enforced at import

`assert_registry_excludes_nothing_it_registers(REGISTRY, EXCLUDED)` runs at module import. Two
tables naming one model is a contradiction in the **data**, not a routing question — so making it
impossible to construct is stronger than reordering `resolve`, and it fails for every consumer of
the library rather than only inside the test suite.

It is a pure function taking both mappings, so the refusal is testable with synthetic tables while
the real ones are checked on every import.

## The other half of the same hole, closed in the same guard

A duplicate `blueprint_model_cell` is invisible to the set-equality test — the set of declared
cells is unchanged, which is exactly how the rogue entry hid. §7 lists one model per cell, and the
shipped data agrees: **15 entries, 15 distinct cells**. So uniqueness is enforceable, and enforcing
it means a new entry has to claim its own §7 row rather than inherit accountability for someone
else's. The realistic trigger is not malice: copy an existing `ModelEntry` as a template, edit
`model_id` and `component`, forget the cell.

## Mutation audit, against a baseline verified green first

```
baseline: GREEN
CAUGHT   the exact rogue entry that slipped through before is re-added
SURVIVED the import-time enforcement call is removed
CAUGHT   the disjointness check never finds an overlap
CAUGHT   the check raises unconditionally (would break honest tables)
CAUGHT   the duplicate-cell check never finds an overlap
CAUGHT   the duplicate-cell check fires on a single claimant too

5/6
```

**The survivor is redundancy, classified rather than patched.** Removing the import-time call
leaves `test_the_real_tables_do_not_both_register_and_exclude_anything` and
`test_an_excluded_model_is_still_refused_by_resolve`, and with the call removed *and* the rogue
entry added, both of those fail — verified. So for gate purposes the call is belt-and-braces. It is
kept for what the tests cannot provide: refusal at **import**, so a library consumer with a
contradictory registry stops rather than silently resolving an excluded model.

Two mutations are the ones that earn their place. *"the check raises unconditionally"* is caught by
the control (`test_disjoint_tables_are_accepted`) rather than by any refusal test — a guard that
rejected honest tables would pass every refusal test here. *"the duplicate-cell check fires on a
single claimant too"* is the same shape for the second half.

## The claim M0.2 makes is now actually true

M0.2's row and the module docstring both say *"Adding a model without amending the blueprint fails
the gate."* I drafted a paragraph here claiming that stayed false in general — and then checked it,
which is the only reason this section says the opposite. The set-equality is **bidirectional**:

* `test_registry_contains_nothing_that_is_not_in_section_7` — an **invented** cell string is caught,
  because the code's cell set gains a member §7 does not have.
* `test_registry_omits_nothing_that_is_in_section_7` — the reverse direction.
* a **duplicated** cell is caught by the uniqueness check added here, which is the case both
  directions of set-equality are blind to.
* an **excluded** id is caught by the disjointness check added here.

Those four cover the ways a model can reach `REGISTRY` without a §7 row of its own, so the claim
holds now. It did not before this commit, and the drafted-then-corrected paragraph is left recorded
because the mistake is the same one this whole file is about: writing down a plausible statement
before measuring it.

Gate: `VERIFY OK — 1125 passed, 0 skipped`.
