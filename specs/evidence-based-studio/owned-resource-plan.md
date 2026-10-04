# Owned Resource Identity Correction

Approved-by: Wareen, existing explicit parent T3/owned startup implementation approval.
No dependency, spending, licence, key, VEX rebind, push or release approval implied.
Baseline7da008f44d76cd47b6e1843e3f1a3833a63f5e73, producer
e8e37994285622371f269862c942664451bfc5f2805e3709c89ad78da98f3eaa.

## Research And Impact

Actual DBOS2.29.0 _sys_db.py:625 wraps the supplied engine once with execution_options
(schema_translate_map). SQLAlchemy2.0.52 OptionEngine retains _proxied. Pool equality
alone does not prove engine events/transaction fencing: a real foreign engine sharing
NullPool passes current owner verification and reads an unsupported journal that the
original engine refuses. No producer/pickle/model/paid call. Original private probe JSON
SHA256db285f3cbfebd12db9f71e89c2e066555760aec4ba3b0730206529063b1fd460,
script/log/database retained externally. Pydantic2.13.4; current host in frozen7da evidence.

Actual four-query cached Serena map before edits: constructor1/0, _verify_owner1/5,
close1/1, embedded _RUNTIME1/2; owned-resource-7da-before-map.json/log. Caller obligations:
launch, owned-engine callback and verify/close (including partial refusal/foreign singleton),
actual runtime subprocess controls and CLI lifetime. Dynamic callers in the embedded string
are supplemented manually by named tests. No ordinary CLI/configuration signature changes.

## EARS

WHEN the actual DBOS database becomes available, THE owned supervisor SHALL prove its
actual pinned OptionEngine directly proxies the owned base engine and capture the exact
database and engine objects before subsequent guarded operations.
WHEN those objects are replaced, lost or borrowed through the same pool, THE supervisor
SHALL refuse read/dispatch and draining cleanup before changing foreign resource flags,
retain its lease and require reconciliation, not recreate or destroy the replacement.
Named evidence: test_owned_runtime_refuses_unowned_database_resources (engine/proxy/
database/missing cases), plus every original30 runtime and native admission/caller case.

## Sequential Implementation

1. Add real resource replacement/foreign flag/lock retention/getter regressions first;
   preserve actual failing diagnostics. No mocking the engine, fixtures or assertions.
2. Capture exact owned DBOS resource identities after actual proxy proof; reject later
   None/drift. Validate ownership before shutdown touches database/thread stop state.
3. Complete unchanged native/caller diagnostics and strict lint/types/format; update
   living docs as WIP. Reviewed local correction commit, exact frozen bash scripts/verify.sh.
4. Terminal immutable evidence and current same-SHA CI requirement; no ledger promotion
   unless the prescribed gate and CI are green. Correct known billing projections next.

BLUEPRINT sections2-5, D-276, OS4/OS5/OS6.7da full gate4728passes/one VEX binding failure,
zero errors/skips,2190.28s; this was a coverage gap, not a passed ownership regression.
No verified candidate/10/10. Billing, protected producer/model/auth/attempt/session/replay/
revision/export and independent/sustained obligations remain. Current HTTP stays refused.
