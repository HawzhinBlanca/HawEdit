# Studio Diagnostic Language Evidence

2026-10-09. Parent approved T5 scope only. Baseline
b6dac9197d86c7aa795257e370e99e038722c3d3; package before01e8cd5a915f012da04f987705a54eaed73d510ad03d79ac978c292986f3dbe3;
final1024616359a2b593cdfb6fc6fca62ad01123c82be3902a1c4f43014fa18aed98.
Actual Serena map SHA1536cc09ad298b7ffa7860ae4772c9a25e108b2a61dbac9ce140fdc1a8ee5e37,
C:/Users/Wareen/HawEditStudioDiagnostics-b6dac91-20261009/serena-map.json.

Host HawaPC01,Windows11build26300,Python3.12.10;
pytest9.1.1/ruff0.9.6/mypy1.15.0/DBOS2.29.0. Browser Codex in-app;
actual installedFFmpeg8.1.1 SHA09948d4cdd0650da6ff5a87577469f2a218dc2615ae379f8f734d24c49de0f73.
No GPU/model/paid provider execution. CPU identified in preceding host record
as Threadripper3990X64cores128logical; this is UI/testing, no inference throughput.

Commands (PowerShell, .venv/Scripts/python.exe actual workspace interpreter):
`python -B -m pytest tests/test_studio_ui_diagnostics.py` first RED10failures.
Preserved test-first.xml. Initial affected.xml260cases/one failure retained.
Then affected-final.xml260pass. Spacing-red.xml10pass/onefailure.
Final command: `python -B -m pytest tests/test_studio_ui_diagnostics.py tests/test_studio_ui.py tests/test_studio_ui_history.py tests/test_studio_ui_source_feedback.py tests/test_web.py tests/test_studio_artifacts.py tests/test_studio_history.py tests/test_robustness_audit.py tests/test_claims.py --junitxml=C:/Users/Wareen/HawEditStudioDiagnostics-b6dac91-20261009/affected-spacing-final.xml -q`.
Actual261pass/0failure/error/skip,32.589JUnitseconds, exit0;
XML SHA7c437c5b471b7cb9c04b660a5bd27501999b8dbc6d81c7cb548724d7779ca1f7.
`ruff check src tests scripts`, `ruff format --check src tests scripts`,
`python -B -m mypy src tests scripts` all exit0/387files; `git diff --check` exit0.
Not exact full gate or same-SHA CI. No ledger promotion or push.

Actual final browser root C:/Users/Wareen/HawEditStudioDiagnosticSpacingAudit-20261009.
Owned native server started18:47:25UTC/stopped18:49:00UTC; controller57692,
original server60908 gone. terminal.json
SHAa2439d4af60a02acecc6926c7b1ccd2d726cf37c95947e23c7fead2f6bfa560d.
browser-observations.json
SHA271722675ecd2498519eb4f839410de18d05955387b17482b0796a4a18a0de68.
Accepted files, saved and reopened through cua_repl:
- 01-history-320.jpg SHA513dc26f341ade822b5eb534f2b7ff332db4e44dbd32459bae61822b63b8faa3.
- 02-history-390.jpg SHA87dc1cad7609bd51eed4edbf3f86d63920cabab6d10d767287fc47859b5c86a4.
- history-390.jpg actual768px SHA390a98c39feac3c1288a2d312a45c45b57d70059e0952d4093658c09243b775b.
- history-768.jpg actual1280px SHA15a95c140758672a243517540b3146bea5942cd73ab238c105d8748eed74436c.

Other current-run wide captures cropped/rejected, not accepted screenshots.
1440DOM widths no-overflow but1440visual gate remains open. Browser API resizing
is asynchronous across tabs; retained observations record actual measured widths.
No browser console errors observed. Actual history/candidate/recovery codes,
English evidence unchanged, Enter/native details, mixed-script direction,
12pxidentity gap, cleared selected-job diagnostics observed. No fabricated clips.

The first final-audit wrapper refused before launching because its template hash
was copied incorrectly from an inherited summary. Fresh full template inspection
and Get-FileHash established actual0036ee29fe07d70a212d0f89d29ad02f38c1e063d6379ab924d64412071ec5e2;
unchanged original template retained. Corrected external wrapper, not security
policy/reviewer evidence. Initial diagnostic audit and failed launch retained.

Source files: src/hawedit/studio_ui.py,tests/test_studio_ui_diagnostics.py;
research/spec/plan/impact/tasks/verification under specs/studio-diagnostic-language.
No runtime/backend/authority/enforcement edit. Full acceptance and independent
review/CI remain unproven; native-editor copy review/NVDA/zoom still open.
