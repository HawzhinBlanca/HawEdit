# Impact map — WSL validator readiness

## Planned source changes

| File | Symbols | Reason |
|---|---|---|
| `src/hawedit/models.py` | `ModelStore._status_for`, byte-status helper, `missing_weights`, byte assertion | Separate immutable checkpoint presence from execution runtime and select the canonical Windows WSL route for rzgar. |

## Planned tests

| File | Coverage |
|---|---|
| `tests/test_models.py` | Windows WSL success/failure, non-Windows/local control, byte-only missing classification, corrupt bytes, single cached runtime probe, operator detail. |
| `tests/test_model_fetch.py` | Exact validator bytes are not scheduled again after a runtime-only refusal. |
| `tests/test_asr.py` | Existing regression continues to prove verification remains active through the complete WSL subprocess boundary. |

## Affected callers

- `ModelStore.status` and `readiness_report` gain accurate canonical-route semantics.
- `ModelStore.assert_available` continues to require a component runnable in the calling
  interpreter; canonical reporting chooses WSL separately.
- `model_fetch.build_fetch_plan` stops conflating loader placement with missing bytes.
- Local visual/grounding adapters keep their host-loader checks.
- `WslOmniAsrProducer` retains all request, path, receipt, and cross-runtime lock protections.

## Compatibility and risk controls

- The registry, manifest schema, model root, and download destinations do not change.
- The Windows-only validator route is selected through an injectable platform predicate so both
  route branches are exercised without skipped tests.
- Runtime proof remains fail-closed and cached. Checkpoint verification remains mandatory before
  either readiness or worker execution can succeed.
