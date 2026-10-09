# Research

Actual first implementation diagnostic corrects the initial capability assumption:
the real Bootstrap PID1 has CapInh/Prm/Eff/Amb=0, NoNewPrivs=1, but
CapBnd=000001ffffffffff. It must be dropped before exposure, not incorrectly
reported as initially zero. Raw actual kernel status and the first four failed
implementation cases are preserved externally. Final custody still requires
all five capability sets zero. This is not a relaxed publication/security gate.

Second real kernel run refused tmpfs mounting at /proc/self/fd/original-root
with EINVAL22. Use the private namespace's existing root pathname for mount
operations, then hold the actual mounted root descriptions; readonly readback
must succeed on that original description. Exposed file paths remain
/proc/self/fd/original-anchor/relative, independent of external root renames.
Never expose a mutable backing bind or infer readonly from the mount call alone.

Baselinebe6531656ad913be625b722160196cb734ab8532, source d0ae33671fbcc0336d4e740c58a0b07a0763daa1321bc117de440e5a9c4ed127. Relevant vault milestone/Canon read before design. Original approved evidence-based-studio phases1--2 and native-worker-owner T3 require protected consumed bytes before worker/DBOS/HTTP release. BLUEPRINT section3 ingest/ASR and sections8.1--8.3 require real measurements; D-308/D-320 provide original scopes/bootstrap, not model admission.

Actual counterexample: readonly Linux bind of a Windows-held430926857byte private copy consumes foreign bytes after deliberately releasing original backing custody. Original7554... becomesf769..., still-readonly mount; fd7b7dbda04f004b140cad91127b04f2d0c57af8e5bfc5134abfebd29d4d212a. Anonymous sealed memfd copy rejects writes but pathname bind fails EINVAL22; raw failures/diagnostic retained. Actual independent owned regular-file copy in512MiBprivate tmpfs, exact hash/size, closed write descriptions, readonly mount/caps0/namespace fence survives the same backing release/source mutation: consumer remains original hash, source foreign. Receipt392915fa2d8fe61358b882d277b8cf5e3c5134a627c1627ce4aa99c43ac82823. None is complete model/runtime admission.

Actual NumPy1.26.4/Torch2.8.0+cu128CPU compatibility under prototype fence, CUDA uninitialized, succeeds. Metadata inventory1020paths/4535270817bytes is not dependency closure. Existing bounded image limit remains256MiB; do not broaden it. Linuxowned interpreter/system files and initial trusted controller custody remain obligations. Full raw commands/versions/provenance: C:/Users/Wareen/HawEdit-producer-adoption-research-aeca0ae-20261009.md.

Fresh actual6Serena definition/reference pairs before edits, source/ref/status unchanged, C:/Users/Wareen/HawEditImmutableSnapshot-be65316-20261009/serena-map.json, b2c389cae555577627a3c505bf8431b9591c5aaa28a95a6db570528230803ff8. NativeJob/create21refs,_open_image3, LinuxNamespaceBootstrap2,its exec0static refs,LinuxScope2,prepare_studio_execution7. Dynamic PRELUDE/alias-generated tests explicitly require mapping beyond LSP counts. Existing bootstrap test execute/observe functions inspected: actual suspended native WSL launcher, system /usr/bin/python3, original pidfds and bounded cleanup; reuse unchanged.

Implement owned finite private readonly file tree and mandatory namespace-reentry fence as a prerequisite, not an execution token. Reject unsupported platform/architecture, ordinary nonnamespace callers, insufficient initial kernel state, unsafe names/files/budgets, copy drift or failed kernel transition. No callbacks, JSON authority, transferred original capability or source mutation. A failed irreversible namespace preparation requires exit/reconciliation, not caller retry. Consumers may only trust a live same-owner object and kernel readback; complete interpreter/source/model/input closure, source rights, qualified security, billing and publication remain separate and HTTP stays refused.

Prior exact gate5959pass/1stale independently qualified-policy binding failure; no agent review/source/date self-rebind. No new dependencies, protected metadata/model/fixture/golden/harness changes, provider/GPU/neural execution or spending. Architecture is recorded in D-323. Memory budget limits copied bytes/tmpfs size, not a claimed totalRSS/cgroup/GPU ceiling. No malicious same-privilege code sandbox claim.

Primary-source API review: Linux kernel seccomp documentation states that filters
inherit across permitted fork/clone/exec and explicitly warns filters are not
a complete sandbox. https://kernel.org/doc/html/latest/userspace-api/seccomp_filter.html
and https://cdn.kernel.org/doc/html/latest/userspace-api/no_new_privs.html.
The mount syscall reference distinguishes filesystem readonly from bind-mount
readonly and documents EBUSY with open writers:
https://www.man7.org/linux/man-pages/man2/mount.2.html.
Actual pinned kernel experiments, not documentation alone, establish this unit.

Actual same-inode reopened-descriptor control exposed a cleanup bug after its
verification correctly refused. Preserve genuine red35pass/1failure XML
670ffdecd94d7e0d0787552726d5a52e6f7a569195b0f1b89c1f717c615f2ceb;
fixed cleanup compares original file descriptions before closing. The earlier
descriptor-number allocation assumption failure and syntax/absent cohort-path
collection failures are retained, not relabelled as behavioral red evidence.
Whole affected275cases pass/zero errors/skips in90.243JUnit seconds; exact
commands, hashes and measured host/controller versions are in
evidence/owned-linux-snapshot-20261009.md. No ledger promotion before gate/CI.
