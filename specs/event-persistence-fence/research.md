# Research

Baseline bd7f567ca486fc63eb826075682334df8b0466e6; producer
9732fc8d3e30dfed3b9eccc8dcee354eb1a290fe4c747c4ce0bf436eb8e521a3.
BLUEPRINT sections 2-5, 7.6; D-274/D-305/D-306. Parent approved execution and
recovery repairs, not cloud/security/publication permission.

Actual decoded fixture ingest with a real event file switched to read-only
after its first committed event raises io.UnsupportedOperation at ingest
completion. run_pipeline catches this OSError and incorrectly returns an
ingest-failure report. It does not complete, bill, or create candidates.
Terminal 831ca67237b1fe8a50e7db84b6779825f9d3dea66ad7ad57972e6afa83bc271d:
C:/Users/Wareen/HawEditEventWriteFault-bd7f567-20261008/terminal.json.
Source/observer/HEAD/producer/status unchanged; HawaPC01/Windows26300/Python3.12.10.

RunEventLog currently lacks a persistence failure latch. It advances sequence
before event validation and directly invokes the sink. AttemptStore is real
FULL SQLite persistence; its write failures already raise StudioStorageError,
but recovery must not permit a failed log to silently continue the same attempt.
Legacy JsonlEventSink flushes but does not fsync; this repair does not promote it.

Actual ten-pair Serena definition/reference map at unchanged baseline:
C:/Users/Wareen/HawEditEventFenceMap-bd7f567-20261008/serena-map.json,
SHA256 f54e67ab5dcec59a65c0ae181b8446c8564035ca346a162617a00180380757d4.
Includes RunEventLog/billed/_emit, JsonlEventSink/__call__, run_pipeline,
_ingest_failure_run, AttemptStore/append/finish, prepare_studio_execution,
GuardedGeminiTransport/_send. Original mapper stopped before edits.

Prior exact dirty gate: 5603 pass/2 fail/3 errors, no skips. Four build results
refused unrelated dirty assessment notes, preserved. Exact same-SHA clean gate:
5607 pass/1 VEX-binding failure, no errors/skips, unchanged clean worktree.
Terminal 0cc6a5c86f55f20fbd9dda5d3dd1d9e6287c4c088979b038fd727439a86080ad;
JUnit 446d1f5a9fcccaa02ade94348fb7971e7a08a69e871e7cdedebd5eebbba96574.
Both original processes absent and sessions closed before corrective edits.

Additional actual constructor/_emit/billed definitions and references after
test-first additions, before production changes: unchanged map
C:/Users/Wareen/HawEditEventConstructorMap-20261008/serena-map.json,
SHA256 f476b1b713478cfb5af9b492130c5487667a8b7963d6964c952fc5b3b5c80b4f.
Original mapper absent before session closure. Valid test-first result:
49 existing passes / 7 expected failures / zero errors or skips. All seven
failed on actual write/refusal/sequence behavior, not missing imports. JUnit
39dad3255e3b7f112948a2999d8d5c7d51a700d3bf1dc96be0e303c55c4e1ff3:
C:/Users/Wareen/HawEdit-event-fence-test-first-20261008.xml.

No measured extra provider calls or false completed publication. The protected
producer must still adopt pre-effect and pre-result admission and full scope/
billing reconciliation. BLOCKED #1/#3/#4/#24/#25 remain, #21 stays closed.

Current first committed full gate at dfa455a finished 5612pass/3fail/0error/skip,
exit1, fully unchanged clean source/observer/HEAD/producer/status. Terminal
103f25de7f6f1b64fa19df082e7a47985b993113174e4ef491968149f72cb438;
JUnit8a7a089df58ce6238165741515c296c6c41fe377db9c69bbcfe7f3f132ff0b04.
Failures: checkpoint caller still expects a raw SimulatedKillError; a Windows
PermissionError replacing a private copied FFmpeg executable; current VEX binding.
No source edits until original gate processes absent/session53467closed.

Actual current checkpoint/refusal/_publish/health four-pair map unchanged:
C:/Users/Wareen/HawEditCheckpointEventMap-dfa455a-20261008/serena-map.json,
df8bb9a285900f02926b4d62da39ff0326d608d3d550dfc65be0245becc62d95.
Whole checkpoint diagnostic5pass/1valid caller failure/0error/skip;
JUnit ee4405fd1df0284dbc2ba54fe5655606b4a780e5dcda5546e1599a1e7c6f414c.
Correct caller expectation must require the distinct error AND exact original
SimulatedKillError class/stage message; every seven-stage resume and actual MP4
hash-equality assertion remains intact. Test description corrected: these are
simulated callback exceptions with test editorial inputs, not actual OS kills.

Whole unchanged ingest-cache module repeat16pass/0failure/error/skip,53.527s;
JUnit78fc792a0c60dfa239c328a90ae549d800177bc8049a98c547a57e12747acd44.
The earlier denied private executable replacement did not reproduce here.
Cause remains unknown; do not attribute it to antivirus or claim it fixed.
Keep the unchanged real binary-drift regression in the unfiltered full retest.
