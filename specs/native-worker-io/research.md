# Research

Parent 2490df244b722f5c35bbf09865c78a5aba12c3bd, producer e92e54512c5bfab67b20396fd55f203e96526fd6c7c1cbe79a2d811b8d008605.
BLUEPRINT sections 2-5/8.3; D-308; native-worker-owner T2. Vault canon and native
worker/pipe ACL notes read before design. One writer; no producer rerouting.

Actual fifteen Serena definition/reference pairs before source edits:
C:/Users/Wareen/HawEditNativeIOCurrentMap-2490df2-20261008/serena-map.json,
SHA256 53ba7293f40c0196a5f0b112df8b1116f61f1c40deb39892fbd6c3bc5019c99d.
Existing NativeJob lifetime and SID/ACL helpers remain unchanged.

Sixteen real external IO faults and four real descriptor readbacks are recorded
in C:/Users/Wareen/HawEdit-native-overlapped-io-research-20261008.md. The default
descriptor returned Win32 87, an uninspectable refusal, not a safe/unsafe ACL
measurement. Never infer completion from CancelIoEx success, EOF or process IDs.

External test-first initial26 and expanded30 cases fail missing native_io.
Expanded JUnit SHA256 aecd97c5c4ca91d7cd0f371a723574e30a82e6e24f6c5ce3727675095b2be889.
HawaPC01/Windows 26300/Python 3.12.10/pytest 9.1.1. Pending writes may initially
fit the kernel pipe buffer; the test fills it until an actual operation is pending.

Parent exact gate:5566/5567 pass, zero errors/skips, exit1 solely qualified VEX
source-binding failure. Source/observer/HEAD/package/status unchanged. Original
processes absent and session86807 closed before source edits. JUnit
fe1bb0133d31194471e17d7490c431d90fef1b70ef79c64b25796072da8e56d2;
terminal be3e82f77ae15a9e5b8a7ff1ac226af2b1f5b7a175f7ea6ba8724621e49ebb66.

Primary references:
[Pipe security](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights),
[Handle descriptor readback](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo),
[Cancellation](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-cancelioex).
No hostile equal-user sandbox, complete native/Linux resource drain, billing,
runtime/VEX admission or publication authority follows from these observations.

Rechecked Microsoft primary completion/cancellation documentation2026-10-08:
[GetOverlappedResult](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-getoverlappedresult)
requires the original operation handle/OVERLAPPED and returns incomplete rather
than waiting when requested. CancelIoEx does not complete operations by itself;
unknown pending results stay retained. CreateNamedPipeW web open was unavailable;
its binding was corrected against the actual preserved eight-argument native
observer and verified by real product pipe creation, not claimed from that page.
