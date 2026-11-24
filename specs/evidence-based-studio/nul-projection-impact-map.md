# Exact Projection Impact

Actual maps: nul-projection-before-map.json _read1/2, outbox _decode1/2,_select1/2;
nul-diagnostic-before-map.json note_dispatch_error1/4, including actual queue caller and tests.
The decoder/selection changes affect _get and _bounded_read, therefore reserve/get/pending/
recovery/dispatch callers. Complete admission/intake/submissions/storage/queue/generation/
claims modules required. No signatures, database columns, snapshots or original jobs change.

Pending must include invalid/null dispatch states for refusal: selecting only literal pending
would silently omit a hidden suffix before the decoder sees it. Healthy confirmed jobs remain
excluded; pending plus malformed selected rows retain the existing finite count/byte/deadline
limits. Actual nul-pending-before-map.json has one definition/29 references. New NULL/type/Unicode/duplicate/budget
controls and all existing assertions stay intact. No repair, truncation or authority gained.
