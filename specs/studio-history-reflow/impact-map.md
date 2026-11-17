# Actual Caller Impact Map

Baseline1a57ba3; actual Serena map path in research.md. Only production edit:
src/hawedit/studio_ui.py's DASHBOARD_HTML constant (definition line5).

Serena references: web import/re-export and HawEditWebHandler.do_GET root/index
response; tests/test_web.py, test_robustness_audit.py, test_studio_artifacts.py,
test_studio_ui.py, test_studio_ui_source_feedback.py. do_GET's do_HEAD caller
also serves the same bytes. Existing import and HTTP signatures remain unchanged.

Embedded-JS supplemental source inspection (rg plus complete function reads):
- refreshHistory line1100: successful generate line894; refresh click1216;
  initialize1303. Preserve historyEpoch and selectionEpoch race fences.
- selectJob line990: refreshHistory1142 and native select change1213.
  Share safe date formatting with labels; preserve explicit user selection.
- diagnostics line940: history success1125 and history error1151.
  Keep raw code/message visible; no translated text may imply a different refusal.
- stages line953: selectJob1018. CSS marker containment affects its ordered list
  and historical diagnostic list only; do not hide overflow globally.
- state line560: add cached history/truncation/selection hint for local filtering;
  no changes to execution, upload, request, preview or readiness state.

New renderHistory/date helpers: refreshHistory and search-input handler; date
helper also selectJob. Filtering must not call selectJob, rewrite selected-storage,
or clear a preview; preserve a nonmatching selected option with a labelled hint.
Refresh must preserve the selected persisted identity if the job is absent.

Regression modules: new test_studio_ui_history.py plus all five existing caller
modules above. Browser assertions on real history supplement structural tests;
neither substitutes for the canonical gate or independent/manual acceptance.
