# Actual Impact Map

Serena baseline b290ae8, source b66d0bfdf759cd65aba8396f2f9589258c399498f90720959eacede99d071f0c.
Map C:/Users/Wareen/HawEditNativeMembersTransitionMap-b290ae8-20261009/serena-map.json.

Changed existing symbol: NativeJob.members. Direct production callers:
- NativeJob.create: exact single suspended original root before release.
- NativeJob.resume: exact unchanged membership before single-use resume.
- NativeJob._retain_members: original observation-only descendant handles.
- NativeJob._quiescent: original root signaled, retained handles drained,
  ActiveProcesses0 and actual complete empty list; serves wait/stop/close.

Transitive runtime caller run_native calls wait and stop. Whole caller tests:
test_native_process.py (creation, image lease, assignment/resume, normal exit,
stop/timeout, root exit not completion, natural descendant exit, context cleanup),
test_native_io.py (pending reads, original owner-death process/member observations),
test_native_io_memory.py, test_native_control.py,
test_native_capability_retention.py, test_linux_control.py.
_ProcessList mapped but no layout or active-member ceiling edit planned.
wait/stop mapped but no algorithm/signature edit planned.

New tests use existing _inputs/_kernel/_observe/_ready/_descendants_code helpers
without editing them; their five-pair map already exists in
C:/Users/Wareen/HawEditNativeMemberRaceMap-b290ae8-20261009/serena-map.json.
No fixture/golden/mock/kernel replacement, acceptance thresholds or regex weakening.
The additional API-error test supplies an actual wrong-type Win32 event handle
to the actual query, then restores the original still-held job. No fake API return.
