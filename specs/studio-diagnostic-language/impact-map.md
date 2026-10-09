# Diagnostic Language Impact Map

Actual three-pair Serena map/hash in research.md, unchanged b6 baseline.

| Symbol / Caller | Impact | Required Regression |
| --- | --- | --- |
| studio_ui.DASHBOARD_HTML | Only production symbol changed;91static references | Whole seven mapped test modules and actual browser |
| web import/do_GET | Serves the same HTML, no route/schema/authority change | Whole test_web/test_studio_artifacts |
| diagnostics -> refreshHistory success/error | Preserve structured records; localized primary copy and original details | Known/unknown codes, textContent-only technical display, actual history error |
| selectJob success -> candidate diagnostics | Use dedicated job list, not raw English concatenation | Adoption/empty/candidate refusal, selection-epoch guards preserved |
| clearJob -> new job diagnostics clearing | Prevent stale diagnostic from old selection | Structural clearing plus actual deselect/select |
| read_history/_candidates/_diagnostic (unchanged) | Five current codes remain API evidence | Whole test_studio_history; no backend translation/rewrite |
| legacy recovery error (unchanged API) | Localized error summary with original details | Stable recovery code; original error remains available |
| markup (unchanged test helper) | Existing semantic parser,5static calls; reused by new tests | Whole test_studio_ui/test_studio_ui_history |

Mapped DASHBOARD_HTML references: src/hawedit/web.py and
tests/test_robustness_audit.py, test_studio_artifacts.py, test_studio_ui_history.py,
test_studio_ui_source_feedback.py, test_studio_ui.py, test_web.py.
JS functions are embedded in a Python constant; above direct call inspection is
supplemental. No existing helper, backend, pipeline, runtime or enforcement
symbol is edited. New test module/functions have no pre-existing definitions.
