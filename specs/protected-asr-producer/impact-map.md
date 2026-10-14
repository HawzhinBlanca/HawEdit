# Protected ASR Impact Map

Current13pair actual Serena map and hash in research.md. Known caller surfaces:

| Symbol | Caller Surface | Required Coverage |
| --- | --- | --- |
| WslOmniAsrProducer.transcribe | Pipeline/ASR context/resume/worker diagnostics | Producer parity, canonical identity/stop/origin/context/reuse |
| asr_worker.run_request | main plus adapter/origin/completion/resume/publication tests | Existing CLI no-clobber and byte-identical canonical inference |
| LinuxSnapshot constructor/fence/inspect | Native default/rooted/entropy/GPU/worker/controller fixtures | All original defaults and stronger final kernel policy |
| LinuxThreadRegistry/Broker | Native original-membership/broker and typed controller | Fixed diagnostic defaults, explicit authorized production bounds, drain |
| LinuxPreparedView | Native original Scope/worker/controller fixtures | Unchanged original prepared/joined kernel evidence |

Before changing additional symbols, capture actual current definition/reference
pairs for RootedCommand/Launch, worker journal/backends, studio host/execution/
runtime/queue/submissions, pipeline builder/asr factories, readiness receipt
publication and selected delivery/review callers. Those maps are pending;
do not invent signatures or edit those symbols until mapping is complete.
No generic callback, raw HTTP pathname, second pipeline or new DBOS queue.

## PA1 Current Controller Map

Actual Serena definition/reference pairs at clean49d36f9:
`C:/Users/Wareen/HawEditGPUControllerMap-49d36f9-20261014/serena-map.json`,
SHA25653736440cb03f137fc38af77ef1b1da35a0346651e17644cbe8df721fa904ac6.
Thirteen pairs cover Snapshot.__init__, _enforce_gpu_policy, _check_gpu_policy,
_inspect_gpu, _fence, _apply_landlock, _install_namespace_fence;
RootedLaunch.__init__, _before_copy, _run; Registry.open_comm, Broker.serve_once;
and tests._controller_run. The inspected source remained unchanged during mapping.

Direct references: Snapshot.__init__ calls policy enforcement and Launch._run;
policy enforcement, _inspect_gpu and _fence call _check_gpu_policy; _inspect calls
_inspect_gpu. RootedLaunch._run installs the controller fence and invokes the
registry/broker. Tests use actual Linux kernels via generated fixtures, which
Serena cannot resolve as Python callers. Retain the complete default GPU,
entropy, rooted worker/controller, registry/broker and Scope/View regression sets.

First PA1 unit establishes an internally installed controller-fence profile and
its exact combined denials. GPU launch remains refused until actual servicing,
final fencing, original descriptors and CUDA consumer tests establish admission.
No change to the default GPU EACCES contract or diagnostic ceilings.

Introduced-profile map before wiring Launch._run: actual three Serena pairs at
unchanged WIP in `C:/Users/Wareen/HawEditGPUProfileMap-WIP-20261014/serena-map.json`,
SHA2565428b7d4eb97748a0bb1b4e5fd4f0237276172c668935b1478e8861d9d60a475.
The newly created Snapshot._controller_fence had no static caller at mapping;
Launch._run is now its sole production caller. Snapshot.__init__ is the sole
production caller of the changed Launch._run signature. Actual ELF/Python tests
add final stacked-filter binding assertions; GPU tests separately exercise
owned installation, exact Landlock/seccomp denials, unregistered filters,
replay and caller boolean refusal. The private profile does not grant GPU launch.
