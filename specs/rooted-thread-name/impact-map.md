# Proposed Thread-Name Compatibility Impact

Actual six-pair Serena map and unchanged-source hash are in research.md.
The narrow plan is approved. T2 production integration remains conditional on
the T1 feasibility and refusal corpus; the 2026-10-12 research matrix establishes
a private-root path but does not yet implement it in LinuxSnapshot.

T1 adds only `tests/thread_name_kernel_probe.py` (a literal native
probe program, executed only by its tests) and
`tests/test_thread_name_kernel.py`. Existing production symbols and the
`tests/test_linux_bootstrap.execute` harness are unchanged. The latter's actual
signature and native 20-second/output-bound behavior were read before use;
the new callers are the T1 fixture and six test families in spec.md. Existing
snapshot/scope/bootstrap Serena definition/reference pairs remain unchanged at
the recorded source digests. New source has no production callers. Every
literal syscall is exercised on the real installed kernel; no SDK/model/API
request or publication is performed by this calibration.

The e243 full gate exposed the initial helper's incompatible placement in the
historical-tool directory. Actual Serena three-pair helper/scope map SHA256
ed8b4ac8c8581b0bc076feadc89c3a8067f207958890abf3d811456c215d77d3 precedes
its move. The only loader is kernel_matrix in tests/test_thread_name_kernel.py.
The existing research-scope test and its exact inventory remain unchanged.

| Existing Symbol | Actual Callers | Required Regression Scope |
| --- | --- | --- |
| LinuxSnapshot._fence | __init__ | Default/entropy/GPU flags remain denied; notification opt-in cannot override a stronger existing denial |
| _enforce_gpu_policy | __init__ | Mandatory Landlock stays active before SDK/model release; no general writable root/proc rule |
| _prepare_proc | __init__ | Original worker proc mount remains readonly and anchored |
| _outside_descriptions | __init__ | Listener/control custody is typed/original/bounded, not arbitrary FD or SCM_RIGHTS admission |
| _check_gpu_policy | _enforce_gpu_policy, _inspect_gpu, _fence | Genuine non-GPU write refusals remain measured |
| _inspect | __init__, verify | Original root/mount/namespace/capability/FD custody remains continuously verified |

Before editing __init__, cleanup, LinuxScope/controller/Bootstrap or any
additional symbol, map its real definition and references with Serena and add
all callers here. Existing symbol maps are not authorization to invent a new
signature. Native/generated constructors must be inspected as supplementary
callers: static references alone do not cover embedded Python programs.

New broker controls require genuine kernel tests for admission, ADDFD atomic
reply, task/namespace lifetime, cancellation, descriptor substitution and
complete original process drain. Test names in spec.md are proposed, not
existing passing evidence. Full affected cohorts must include snapshot,
rooted-image, entropy, GPU, bootstrap, scope, native I/O and model/worker claims.

## Supplemental Lifecycle Map

Actual installed Serena ten-pair LSP map at unchanged94/source status:
C:/Users/Wareen/HawEditRootedBrokerLifecycleMap-20261011/serena-map.json,
SHA256 47ca2e95e65d6231cbd45e69874cf716d1f71f8a8ed79ba2795de945cb436210.
No active mapping processes remain; source remains unchanged.

| Existing Symbol | Actual Static Callers | Design Constraint |
| --- | --- | --- |
| LinuxSnapshot.__init__ | None returned; inspect embedded constructors | Original single-thread PID1, one irreversible preparation; no unsafe/unfenced public mode |
| _cleanup | __init__, close | Close only owned original descriptions; controller/broker drain remains mandatory |
| _drop_caps | __init__ | All capability sets zero before untrusted SDK or broker release |
| _enter_root | __init__ | Actual private root/cwd and closed outside-directory handles |
| _initialize | __init__ | Original nested user/mount isolation; no propagation to creator |
| LinuxScope._admit | __init__ | Original namespace/pidfd relationships and independent description anchors |
| LinuxScope.require_live | __init__ | Original owned lifetime, not a rediscovered PID or cached readiness flag |
| LinuxScope.stop | None returned; native strings are supplemental | Original initializer/member pidfd cancellation and complete bounded drain |
| LinuxNamespaceBootstrap.exec | None returned; native strings are supplemental | Original direct child/owner death/fixed executable custody |
| LinuxNamespaceBootstrap._isolate | exec | Close inherited outside handles, genuine null stdio, declared controls only |

The existing snapshot enforces Landlock in PID1 before worker fork. Therefore
a sibling broker cannot simply be forked after the constructor and open a
writable comm leaf: it inherits that policy and readonly proc mount. T1 must
prove a separate trusted, original, private-root controller/proc capability
before T2 selects any lifecycle integration. No generic callback, unchecked
deferred fence, unrestricted SDK parent, or writable task-directory rule is
authorized by this map. Additional helpers still need their own current map.
