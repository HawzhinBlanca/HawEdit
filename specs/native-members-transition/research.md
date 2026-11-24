# Native Member Transition Research

Baseline b290ae8766b0ea47686de368083730318554d283, 2026-10-09.
Vault: Projects/HawEdit bounded native IO repair 2026-10-08; owner canon read.
BLUEPRINT sections3/5/8.3, D-308/D-311: held original resources remain mandatory.
BLOCKED #24: independently reviewed current VEX remains unavailable.

Actual clean full gate:5702pass/2fail/0error/skip; launcher-exit test failed
in0.159s with "Native member enumeration is incomplete". It must still refuse
completion while the real descendant lives, then terminate the owned job at its
deadline. The unchanged isolated39-case module passed; this is a flaky refusal,
not evidence of a corrected implementation. Exact assigned/returned counts were
not captured in that run. Full terminal:
C:/Users/Wareen/AppData/Local/HawEditEvidence/linux-owner-doc-clean-gate-20261009/terminal.json
SHA2562445e051ade74299215af99208e9fea787a6aa02d8eb586653c38481d8a3ed8f.

Actual Serena definitions/references before edit:
C:/Users/Wareen/HawEditNativeMembersTransitionMap-b290ae8-20261009/serena-map.json.
All four pairs resolved; source/HEAD/status unchanged. Earlier five-pair map also
covered _retain_members/_quiescent and actual test helpers. See impact-map.md.

Microsoft documents NumberOfAssignedProcesses as IDs to store and the returned
count as valid buffer elements. A short list is not complete evidence:
https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_process_id_list
https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-queryinformationjobobject
The job has an actual64-active-process limit and a64-ID buffer. A bounded fresh
query may recover a changing observation; API failure, over-capacity, or counts
remaining inconsistent must still refuse. No interpretation of a partial list
as empty, no new lifetime, no release from only root exit or only accounting.

Chosen scope: members only; add actual kernel transition regressions. No model,
GPU, provider, worker admission, VEX rebinding, IO-policy or canonical ASR edit.
