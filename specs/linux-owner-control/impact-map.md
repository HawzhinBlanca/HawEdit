# Actual Impact Map

No existing source symbol is edited. New hawedit.linux_control.LinuxOwnerChannel
uses stdlib only and has no production caller before this unit. Its first caller
is the new real-pipe test module; no arbitrary source/HTTP callback is introduced.

Current actual Serena map437e6dd727d002706394388be2d6771641e170a7ac444308f6ec2572d4a08109
maps run_native/_ControlExchange and original NativeJob create/stop/close plus
WSL producer, runtime close and attempt finish. Existing native execution stays
unchanged. Windows/WSL test bridge uses the actual run_native; Linux CI uses
actual original child pipes and bounded test driver, not mocked protocol IO.
No WSL availability failure is silently skipped or counted as executed Linux proof.

Keep entire native_control/native_io/native_io_memory/native_process/
native_capability_retention modules in affected checks. Current storage/billing/
runtime/host/model-fetch callers retain their exact tests. Existing ASR/canonical
serde, model checkpoints, engine/configuration, queue, attempts, HTTP, signatures,
fixtures/goldens/harness and runtime dependencies are not changed.

Private control FDs are non-inherited, but the endpoint does not spawn a worker
or guarantee its STD separation. Actual supervisor integration must satisfy that
contract before release. A closed control pipe cannot release a durable attempt.
# Corrective Actual Map

After the new test-first implementation, actual Serena definitions/references
were captured for LinuxOwnerChannel, _deadline, execute and the four affected
test functions before correction. Seven pairs, unchanged source/HEAD/status:
C:/Users/Wareen/HawEditLinuxControlCorrectionMap-20261009/serena-map.json,
SHA2563712c8eb6bbea2252c71d2ae4f4531ccdebc28c4d7b75792b80c26eeabca416d.
No existing production caller is added. Child tests compile exact current module
bytes; string-contained calls supplement static references, not production
admission. Add creator/type annotations and portable stdlib access only; repair
the real test private-parent preparation, never weaken protocol assertions.

# Blocking Helper Map

Actual helper definitions/references before their portable-access correction:
C:/Users/Wareen/HawEditLinuxBlockingHelperMap-20261009/serena-map.json,
SHA25624f9c99594a14f56931c084d80d22361a0e41bb33c1f162a21f888c5b4d2568a.
_get_blocking serves constructor/guard; _set_blocking serves constructor/close.
All callers stay covered by the whole protocol module. Two pairs, unchanged.

# Anonymous Pipe Admission

Actual constructor/_identity definitions and references, two unchanged pairs:
C:/Users/Wareen/HawEditLinuxAnonymousPipeMap-20261009/serena-map.json,
SHA256e30478e0c4babacd06a5237215909a36e3534d1fa8dab55f691ec60350f31a40.
_identity serves constructor and _inspect; latter serves every IO and close.
Real Linux named-FIFO red was accepted incorrectly; whole50case report has
49pass/1failure, not a preparation failure. Add anonymous pipe proc-FD check
to every identity inspection; no new existing pipeline caller.

# Original Owner Guard Map

Actual three-pair constructor/_creator_check/_inspect map before hardening:
C:/Users/Wareen/HawEditLinuxOriginalOwnerMap-20261009/serena-map.json,
SHA2569e6db2e912ff5aa7889cbd54990e019d9db4d83e420dd64be282d54acf4ccbbf.
_creator_check serves every IO and close, _inspect serves adoption/guard/close.
New actual same-inode reopen and recycled-thread regressions supplement prior
whole574case unchanged baseline. No existing production caller or signature change.

# Portable Description Helper

Actual helper map before portable fcntl access correction, one unchanged pair:
C:/Users/Wareen/HawEditLinuxDescriptionHelperMap-20261009/serena-map.json,
SHA25668f869b7a87fe6cb02daac4481d173402ff709e27e92ff57bf87a3fb66fc0a14.
_same_description serves constructor calibration and every _inspect caller.
Windows typeshed lacks fcntl.fcntl; dynamic callable validation preserves the
actual Linux syscall, with no mocked response or unsupported-host fallback.
