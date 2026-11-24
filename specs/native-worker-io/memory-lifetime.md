# Native Arena Correction

Approved-by: Wareen, approved parent phases1-2 and renewed full-fix instructions;
scoped T2 correction2026-10-08. No spending/trust/security/release expansion.

## Research

At65bb556, _NativePipe owns ctypes.create_string_buffer and _Overlap storage.
Strong _QUARANTINE protects live-process objects, not Python module teardown.
Pending native IO must not reference storage Python can reclaim during shutdown.
No observed corruption is claimed. BLUEPRINT sections2-5/8.3; D-309; #24 remains.
Microsoft VirtualAlloc/VirtualFree specify process-owned reserved/committed pages
and explicit release using original base/size0/MEM_RELEASE. Use read/write only,
never executable memory. No atexit callback or guessed completion.

Sources: https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualalloc
and https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualfree
and https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-memory_basic_information.

## Caller Impact

Actual definition/reference pairs in external current6-target map
C:/Users/Wareen/HawEditNativeIOMemoryMap-65bb556-20261008/serena-map.json,
SHA256af85fd55254407f4bffc3ed0675e1581677d176801396d30b28a446be6ff726b;
source/observer/HEAD/status unchanged. _libraries -> private ACL / constructor;
constructor -> run_native and real private-pipe tests; close -> constructor,
run_native empty/delivered input and finally cleanup, direct actual tests;
_finish -> transfer and cancellation drain; _retain -> pipe/job cleanup.
Public run_native has no production producer callers yet. Existing35actual
IO cases plus native process/private storage/fetch/claims modules cover callers.
No existing test function changes planned, only new tests and helper symbols.

## EARS

WHEN a pipe is allocated, THE executor SHALL use a distinct native read/write
arena for buffer and aligned OVERLAPPED, with non-owning ctypes views.
Test: test_native_io_arena_is_native_and_released_after_drain.

WHEN cancellation is requested, THE executor SHALL preserve that arena until
actual terminal completion, then release it after owned handles are closed.
Test: test_native_io_native_arena_survives_cancel_request.

WHEN Python views are collected during actual pending IO, THE native arena
SHALL remain committed until explicit observed cleanup or OS process teardown.
Test: test_native_io_pending_arena_survives_python_owner_collection.

WHEN original IO cleanup is uncertain, THE executor SHALL retain the native
arena and refuse another launch. Test: test_native_io_uncertainty_keeps_native_arena.

## Sequential Plan

1. Preserve prior gate and lifetime finding; actual map before correction.
2. Add independent VirtualQuery and actual pending IO regressions first;
   preserve external red JUnit without modifying existing expectations.
3. Allocate8192-byte VirtualAlloc arena per channel (4096buffer, aligned OVERLAPPED
   at offset4096), from_address views; explicit checked VirtualFree only after
   known completion and handle cleanup. Constructor failures clean safely.
4. Whole affected tests/static checks, reviewed local-only commit, exact full
   gate and vault capture. Do not touch unrelated untracked assessment notes.
   Dirty diagnostic provenance cannot replace clean gate or same-SHA CI.

Status: WIP. Prescribed ledger promotion only after required green gate and CI.

Initial red JUnit690039dd2876ec2bd43be2ac90d8d28b2ea9bd20c3be12f6f118ff5b80708ce7:
5actual missing-arena failures; sixth child test import failed before exercising
arena, so that case is not valid red product evidence. Corrected to independent
inline native query (base interpreter has no pytest/test-package dependency).
Actual3-pair new-test corrective map before edits, unchanged; external
C:/Users/Wareen/HawEditNativeArenaTestMap-20261008/serena-map.json. Original mapper
absent before71647 closure. Existing production6-pair map precedes source edits.
