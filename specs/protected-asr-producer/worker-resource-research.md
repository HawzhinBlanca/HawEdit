# PA2 Original Worker Resource Unit

Authority: approved protected-asr-producer/plan.md, step2, D-329; BLUEPRINT
sections2-5 and8.1-8.3. This is a narrow prerequisite, not producer admission.

Actual Serena SDK definition/reference map before edits at15915027a9da2857dc8b6cabaa1e827cd8bca4f1:
C:/Users/Wareen/HawEditWorkerResourcesMap-1591502-20261014/serena-map.json.
Four pairs, unchanged=True. RootedCommand is used by RootedLaunch, _execute,
_copied_executable and declaration tests. _execute is called only by
execute_original_worker. _controller_run has the actual controller tests as
callers. Generated INIT fixtures additionally construct RootedCommand: Serena
does not resolve their string content. Preserve positional constructors and
all CPU/GPU/controller/Scope/View/registry/broker regression modules.

Existing diagnostic ceilings remain30s,64KiB,4096files,64births,32requests.
Add an optional exact immutable resource declaration, enforced only in original
single-thread PID2 after capabilities are dropped, before copied executable or
SDK release. Use actual Linux setrlimit/getrlimit: equal soft/hard RLIMIT_AS,
RLIMIT_CPU, RLIMIT_NOFILE, and zero RLIMIT_CORE. Refuse unsupported kernels,
non-original process, malformed declarations or limits that would raise an
already stricter inherited hard limit. Never modify controller/shared limits.
Keep diagnostic bounds:64MiB-8GiB virtual address space,1-30 CPU seconds,
64-4096 descriptors. These are explicit opt-in diagnostic limits, not a full
SDK/model resource policy. No privilege, new dependency or writable path.

The Linux manual documents inheritance across exec, shared process limits for
threads, ENOMEM/EMFILE and hard CPU SIGKILL. RLIMIT_RSS is ineffective on modern
Linux; RLIMIT_NPROC affects a real user's tasks and is not an owned-thread guard.
Do not use either as evidence. RLIMIT_AS does not bound VRAM/driver effects or
the controller's copied image. Those remain separate PA2 admission requirements.
Reference, inspected2026-10-14:
https://man7.org/linux/man-pages/man2/getrlimit.2.html

Test-first: copied existing Python in genuine readonly private root measures
the four exact kernel limits, attempts an actual oversized allocation, exhausts
descriptor creation, tries to raise hard limits and checks another original
thread's limits. Separate actual busy-loop death must be kernel SIGKILL with
original registry drain and authenticated controller completion. Repeat the
memory/descriptor/thread proof with genuine GPU endpoint and final GPU policy.
No substitute model/transcript or mocked resource syscall proves this unit.

EARS: WHEN a resource declaration is present, THE original worker SHALL enforce
and read back exact finite kernel limits before copied execution.
Tests: test_rooted_controller_actual_worker_resources_survive_exec;
test_rooted_controller_actual_gpu_worker_resources_survive_exec.
WHEN CPU consumption reaches the hard bound, THE controller SHALL report actual
SIGKILL and reap the original members before final completion.
Test: test_rooted_controller_actual_worker_cpu_limit_kills_and_drains.
WHEN resource bounds or their type are invalid, THE command SHALL refuse without
reading input bytes. Test: test_rooted_worker_resource_declarations_refuse.
WHEN no resource declaration is supplied, THE diagnostic command SHALL retain
its existing defaults. Test: test_rooted_worker_resource_defaults_unchanged.

Implementation task: tests red; exact immutable limits plus worker call;
affected caller tests; exact bash scripts/verify.sh; retain every failure and
record hashes/runtime. No ledger promotion without green gate and same-SHA CI.
Current qualified independent VEX remains required before model release (#24).
