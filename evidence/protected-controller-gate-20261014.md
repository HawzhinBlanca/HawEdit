---
commit: 49d36f923a154d38a1f96cb72540aabd98f6f58d
media_sha256: n/a (canonical regression gate, not video inference)
host: HawaPC01 Threadripper3990X Windows26300 CPython3.12.10; WSL6.18.54.1-microsoft-standard-WSL2
command: bash scripts/verify.sh
status: WIP; exit1, independent VEX source binding fails, no gate or CI pass
libraries: pytest9.1.1 ruff0.9.6 mypy1.15.0
---

# Protected Controller Canonical Gate

- Date: 2026-10-14
- Git SHA: 49d36f923a154d38a1f96cb72540aabd98f6f58d
- Media: N/A; automated regression suite, not ZAR inference or delivery
- Hardware: HawaPC01, Threadripper3990X, Windows26300; native Python3.12.10;
  WSL kernel6.18.54.1; copied Python3.12.0 where native worker tests execute
- Libraries: pytest9.1.1, ruff0.9.6, mypy1.15.0
- Command: `bash scripts/verify.sh` using `C:/Program Files/Git/bin/bash.exe`
- Result: exit1; ruff/type/format pass;6400passed,1failed,0errors,0skips;
  pytest2750.61s, JUnit2749.950s. No gate or CI pass and no ledger promotion.
- Package SHA256: cffc9b589c8d3d066e36340f9150d2ca7dc0e73fa760da276a9990000ec942fa
- Raw log: `C:/Users/Wareen/HawEditGate-49d36f9-20261014.log`
  SHA256b27482b238f9199103483c61a102deb287e7f2f004e8cf6b23da34c72131dd43
- Unchanged JUnit copy: `C:/Users/Wareen/HawEditGate-49d36f9-20261014.xml`
  SHA25682149a7969e6b56f94ae81553a62ea5a987706bfbd3f68829362e43654fe0067

The sole failure is
`test_checked_in_policy_binds_current_lock_and_assets_and_closes_report`:
the checked-in independent VEX binds old source81f6f606..., not currentcffc9b58....
The review is also expired under BLOCKED #24. No policy rebinding, renewal,
test suppression or gate bypass was performed. Diagnostic engineering evidence
does not authorize model release or demonstrate a content-aware captioned reel.

## Approved Community-1 Attempt

Wareen explicitly approved the pinned Community-1 download after this gate.
Exact existing command:
`.venv/Scripts/python.exe -m hawedit.model_fetch pyannote/speaker-diarization-community-1`.
It returned1 before downloading: checked-in integrity metadata still records
five unavailable LFS hashes. The saved token's pinned access needs authenticated
metadata reconciliation, not guessed hashes or an integrity-policy bypass.
Raw refusal: `C:/Users/Wareen/HawEditCommunity1-fetch-49d36f9-20261014.log`.
No model or licence substitution, package installation, cloud inference or publication.
