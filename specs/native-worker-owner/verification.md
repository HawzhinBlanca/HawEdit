# T1 Verification

2026-10-08, parent c898073a8d43372776e09e3ed7ad473c68f3415f; HawaPC01,
Windows11build26300, native Python3.12.10, pytest9.1.1, ruff0.9.6, mypy1.15.0.
Actual commands: .venv/Scripts/python.exe -m pytest tests/test_native_process.py
-q --junitxml=<fresh external path>; ruff check/format and mypy --strict on both
new modules. Test suite timing is diagnostic, not pipeline performance evidence.

Raw reports under C:/Users/Wareen, preserved rather than overwritten:
- HawEdit-native-owner-test-first-20261008.xml: collection error while new native
  module absent, SHA256e29aca67404580c3e8c1ea0f4453972fa9582018c3edd4c84eda8fc01af4d612.
- HawEdit-native-owner-first-implementation-20261008.xml:26cases/23pass/3fail,
  malformed child-script extra brace. SHA256
  037753e9f5f37cad8861da04f556b85803ac82e654fb4f94a7f48f75cc404e02.
- HawEdit-native-owner-corrected-20261008.xml:26cases/25pass/1fail; empty job
  but descendant original handle WAIT_TIMEOUT. SHA256
  184eb97db2ab20fc7873503569a62e499ac76a8ddc9cd89f88b43f7522b3bd64.
- HawEdit-native-owner-retained-handles-20261008.xml:39pass/0fail/error/skip,
  3.955s diagnostic. SHA256
  cbfdc25e645561f8613b732476c16f7a5c3f37bec3c4d8e9a88fabbf7688f2fc.

Independent observer handles assert actual identity/image/membership/liveness and
signaling. Test coverage includes wrong inputs/hash/STD resources, suspended
assignment, one resume, unrelated inheritable sentinel isolation, actual read
lease on a TEMPORARY copied launcher, original-handle shutdown, deadline,
launcher exit with surviving child, natural child drain, context cleanup and
actual owner os._exit(87). No owner mocks, skipped tests or assertion weakening.
Exact original commands absent before required sessions closed; no Ctrl+C,
foreign process kill, detached verification, model execution or protected edits.

Whole exact committed bash scripts/verify.sh remains pending at this document
write, not green. Same-SHA required CI also absent; every task stays WIP. Never
rebind qualified VEX #24 merely to fix that expected whole-suite refusal.
Complete producer-resource handshake/bounded IO/Linux/model+owner admission,
DBOS/HTTP/review/export and independent sustained quality acceptance remain.

Previous caption T2 final exact c898073 gate now finished5518/5519pass, one stale
VEX source binding, zero errors/skips; all337 affected cases pass and watched
source/controller/HEAD/package/status unchanged. Raw frozen gate.xml SHA256
eb0a13307453253bfb0641c35dc4001dfa748f2a298fdaaafbf9adb153ea0ba4 at
C:/Users/Wareen/AppData/Local/HawEditEvidence/caption-context-full-gate-20261008.
Earlier PROGRESS M9.85 "pending" wording is historical, not the latest result.

## First Exact T1 Gate And Inventory Correction

Clean f41b4f7153cc02d7ea1d1e572c5a9a8316274856, package
978b43ba9e673516ae720662c1984321fa6f044722cba6f0227919cbdf400e60:
exact bash scripts/verify.sh finishedexit1,5556/5558pass,2fail,0errors/skips.
Whole lint/strict types/format358pass. One failure omitted native_process.py from
README's complete module inventory; other is historical qualified VEX binding.
All39native cases pass in the whole report. Every tracked/controller/HEAD/package/
status unchanged and checkoutclean. JUnit2247.344s/controller2277.6902196s,
concurrent diagnostic, not pipeline performance; same host/library versions above.
Original controller40136/launcher47876 absent before session95069closed.

Raw native-owner-full-gate-20261008 under AppData/Local/HawEditEvidence,
gate.xml SHA256290616ba21e3a9a04d2c7451567637ecb5cff256111c3c3fdf905f772844f351,
terminalSHA256bc661196a8f6bfb77ba1c175c20d48c4d2470e712849ced4157cb236ce4eb0d5.
Preserve original failure, do not edit its tests/report or gate. Add the missing
truthfully scoped WIP inventory row; no source behavior change. Fresh actual
Serena definition/reference pair for the unchanged assertion, unchanged source/
HEAD/status: C:/Users/Wareen/HawEditNativeReadmeCallerMap-20261008/serena-map.json
SHA2567b7467a8478926bdd13377307339a0f3378051f9b6731d727fe6636df849bcfa.
Whole claims module and exact corrected committed gate remain required; no DONE,
qualified review, CI or publication inference from the inventory correction.

Whole unchanged claims plus native modules after inventory correction:106pass,
0fail/error/skip,15.125s diagnostic. Command .venv/Scripts/python.exe -m pytest
tests/test_claims.py tests/test_native_process.py -q
--junitxml=C:/Users/Wareen/HawEdit-native-owner-inventory-correction-20261008.xml.
RawSHA256cbc3d4599eb7c5175d7e84502fa74166c09f36ca4675e3b3fb60a0a4d8d3d6c8.
Original command absent before session11966closed. Reviewed document-only local
commit and fresh exact full gate follow; no source behavior or assertion changes.

## Corrected Committed Gate Result

Frozen clean 1400a204ca08ed0ae52ea993ff9a3908164ebafc exact gate exits 1:
5557/5558 pass, zero errors/skips; sole stale qualified VEX source binding failure.
All native/inventory regressions pass in the whole run. Source/observers/HEAD/
producer/status unchanged. Original processes absent before session 43352 closure.
AppData/Local/HawEditEvidence/native-owner-readme-full-gate-20261008/gate.xml
SHA256 b1c4c4f51771143daedb02b6b22e45ecf2b8aa135515ca849acbf600214276b7;
terminal d10168e695d3d11df6ed68f2859f033bca31fd6b50beb2e375cbb76f8c397e1d.
JUnit 2307.563s/controller 2329.7697888s diagnostic on the host/versions above.
No green required gate/CI, DONE or completed-system claim. Next private-evidence
alias repair is independently scoped in specs/private-evidence-alias; bounded IO
and complete native/Linux producer handshake remain required after that repair.
