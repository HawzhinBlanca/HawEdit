# Actual Impact Map

Fresh20 actual Serena pairs/hash in research.md. Existing symbols are unchanged
in T1: introduce native_process.NativeJob/NativeProcessError as a new native
lifetime component. There are no existing code callers of this new API.

Future integration affects prepare_studio_host_transport (6refs),
prepare_studio_execution (7), OwnedStudioRuntime (7), AttemptStore.begin(20)/
append(12)/finish(3), SignedStudioTransport.inspect_effects(3)/_check(7),
WslOmniAsrProducer.transcribe(6),create_omni_asr_producer(11),_build_and_run(13),
RunEventLog._emit(3),submit_studio_workflow(12), checkpoint safety helpers and
PrivateDirectory.verify(30)/open_new_file(9)/member_identity(23). Counts are
actual reference occurrences, not independent execution paths or test counts.
Raw map lists every actual caller, including test modules and exports.

T1 adds new actual-native tests only. Tests use private temporary storage,
harmless finite stdlib children and independent original Win32 observation
handles. Unsupported hosts verify refusal, not claimed native ownership coverage.
No alternate pipeline entry point, provider/model execution, callback adoption,
queue/attempt transition or HTTP change occurs in this lifetime-only unit.

Before changing future integration symbols, refresh actual Serena definitions/
references and test every affected caller. T2 needs separate bounded IO coverage;
Linux scope remains a separate capability. Whole tests and exact gate required.

Corrective maps (actual definitions plus callers, source/HEAD/status unchanged):
HawEditNativeOwnerCorrectionsMap-20261008/serena-map.json23pairs, SHA256
848f387d6c9c85c3de6e3178e36208d45b1f4d01abeb3c13c52cfbe084af80a0;
HawEditNativeOwnerShutdownMap-20261008/serena-map.json16pairs, SHA256
117c8ebaba286e5d3d8096658c6556dbe0c86d59f861f7d331419b8add7af676;
HawEditNativeOwnerFinalizerMap-20261008/serena-map.json1pair, SHA256
48e969c95ba2a4cb5c196cfab116a8b2d1f2ef2611e73923b1e8ebc9e1541097.
These cover all modified launch/lifetime/native ctypes/environment/helper symbols
and existing changed test callers. Exact raw maps are under C:/Users/Wareen.

First exact gate identified README's inventory omission. Document-only correction
does not alter library API or assertion. Actual unchanged named claims assertion
definition/reference pair: HawEditNativeReadmeCallerMap-20261008/serena-map.json,
SHA2567b7467a8478926bdd13377307339a0f3378051f9b6731d727fe6636df849bcfa.
Run whole claims module and exact gate, preserving original2failure evidence.
