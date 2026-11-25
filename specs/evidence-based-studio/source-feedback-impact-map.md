# Source Feedback Impact Map

Actual pre-edit map: C:/Users/Wareen/HawStudioAudit-fe04-20261005-v2/serena-feedback-map.json.
Baseline fe04ce0cd655f12b5b520adf9345fd71cbb239f0, unchanged full source hashes.

- studio_ui.DASHBOARD_HTML: 81 reference occurrences, not 81 independent callers.
  Web re-export and HawEditWebHandler.do_GET serve these exact bytes; do_HEAD
  delegates to do_GET. Preserve imports, GET/HEAD signatures, headers and routes.
- tests/test_web.py: imports and branding/stepper contract.
- tests/test_studio_ui.py: markup, semantic controls, request/upload/history,
  persistence, assets, CSS contrast and superseded-request structural contracts.
- tests/test_studio_artifacts.py: pinned offline font/asset contract.
- tests/test_robustness_audit.py: failed/missing/disconnected UI contract.
- New test_studio_ui_source_feedback.py: scoped structural callback regressions;
  separately repeat native browser source A upload -> source B selection.

Only embedded source-selection callback changes. Browser event dispatch cannot
be inferred from Python LSP references; it was reproduced in the actual app.
No upload/API/backend/queue/parser/model/billing signature or behavior changes.
Run all five listed caller modules, native browser before/after, then the exact
full gate on reviewed clean committed source. Do not label structural tests as
executed browser behavior or full AA/native-editor acceptance.
