# GPU Boundary Caller Impact

Current93d1c3e, actual nine-pair Serena map and hash in research.md. No source edits.

| Existing Symbol | Actual Callers | Coverage Before Adoption |
| --- | --- | --- |
| LinuxSnapshot.__init__ | No static refs returned; generated rooted/entropy/SDK constructors inspected directly | Existing positional/API defaults; rooted-only explicit GPU opt-in, genuine consumer |
| _declarations | __init__ | Type/mode/collision prerequisites before irreversible transition |
| _outside_descriptions | __init__ | Original GPU O_PATH custody only; unknown/writable/reopened/ring/network descriptions refuse |
| _fence | __init__ | Default entropy write denial unchanged; explicit GPU variant requires prior leaf policy, never global write allowance alone |
| _inspect | __init__, verify | Original private GPU/kernel policy custody and all previous image inspections |
| _cleanup | __init__, close | Close only owned descriptions; foreign replacements remain open; drain original scope |
| _acquire_entropy / _prepare_entropy | __init__ | All entropy-only tests and actual readonly kernel endpoint behavior unchanged |
| _drop_caps | __init__ | NoNewPrivs1 and zero caps before private SDK/GPU release |

New GPU/Landlock helpers have no existing symbols. Map their actual references
after first implementation and before fixes. Map any additional existing helper
before editing it. No broad worker/pipeline rewrite, production adoption or
capacity claim follows from this caller map. Existing rooted/snapshot/entropy/
bootstrap/scope/native-I/O/model-loader and claims cohorts remain collected.

Additional actual Serena map: HawEditRootedGPUHelpersMap-20261011/serena-map.json,
SHA111e31548e9d4da2f6f6629a3976fcdb896d840f186536668db867f18cf5d654,
three pairs, unchanged93d1c3e. _libc is called by __init__ and native entropy
tests; _rooted_run by rooted/entropy tests, _run by snapshot/rooted/entropy tests.
These helpers are reused, not changed. New GPU tests first:22 fail from absent
GPU keyword/declaration API,1 default-off positive passes; no kernel substitutes.
Explicit control_fds declares borrowed original unnamed AF_UNIX/SOCK_SEQPACKET
channels; it never grants device/path access. GPU mode refuses any undeclared
pre-policy socket, pipe, device or anonymous I/O description. Only Bootstrap's
fixed null stdio and declared readonly executable descriptions are retained.

First implementation actual new-helper map: eight definition/ref pairs,
HawEditRootedGPUImplementationMap-20261011/serena-map.json,
SHA6d036c5068732c8709bd1f0c7a5e6b68b5f507cf4862c40028ab77f07ffd92ce.
_gpu_outside_description<-_outside_descriptions; _acquire_gpu/_prepare_gpu/
_enforce_gpu_policy<-__init__; _gpu_custody<-acquire/prepare/check/enforce;
_check_gpu_policy<-enforce/inspect_gpu/fence; _inspect_gpu<-_inspect;
_gpu_run<-the new native GPU regressions. Map unchanged while acquired.
Native first implementation refuses GPU custody: host root UID0 legitimately
maps to65534 in the private uid1000-only namespace (actual unshare observation).
Correct by checking host ownership at original O_PATH acquisition BEFORE
unshare, retaining FD/anchor/device/type/link/noninheritability checks afterward.

Correction to that intermediate hypothesis: Bootstrap.exec already creates the
uid1000-only user namespace, so LinuxSnapshot cannot observe host UID0 even
before its own unshare. Second actual native refusal confirms this. Do not use
namespace-relative UID as host-ownership proof. The approved genuine endpoint
contract is fixed no-follow /dev/dxg character10:258, single-link, original
O_PATH descriptor+anchor custody; it does not require an invented host-UID test.
Keep those exact checks and all original tests; remove the new invalid UID
assumption. No arbitrary device name, FD or endpoint allowlist introduced.

Final control correction map: actual three pairs in
HawEditRootedGPUControlMap-20261011/serena-map.json,
SHA627718e598025e32b9d28955d5edc38fb77eed071c04a865471a3ac6c73c3804.
_gpu_outside_description<-_outside_descriptions; new exec/nonblocking tests
have no static refs (pytest entry points). Actual nonblocking FD regression
reproduced admission through wrapper getblocking; check kernel F_GETFL instead.
Preserve copied-Python exec positive/EACCES negative; fix the newly added test's
accidental function-boundary placement, not any existing fixture or assertion.
