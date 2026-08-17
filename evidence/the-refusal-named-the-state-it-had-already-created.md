# The refusal named the state it had already created

`write_credential` narrowed the file **after** writing the key into it. So when the narrowing
failed, the plaintext key was already on disk at inherited permissions and the panel printed:

> Refusing to leave a credential at inherited permissions.

It had already left it there. Measured on hawapc01, 2026-08-12.

## How it was found

A guard-revert sweep over `src/hawedit/credentials.py`: every `raise` in the module, located by
parsing rather than by grep — so a refusal cannot hide from the sweep by being worded unusually —
replaced one at a time with `pass` at the same indent, `ruff format`ed, and the **whole** suite run
against a baseline verified green first. D-149's method, pointed at the module that writes secrets
to disk.

```
refusals found by AST: 10
baseline: GREEN

HELD    line 170  cannot ask git whether {path} is ignored        by 4 test(s)
HELD    line 172  {path} is not ignored by git                    by 2 test(s)
HELD    line 194  {name} is empty — that is not a credential      by 1 test(s)
HELD    line 230  {env_file} is a symbolic link (pre-open check)  by 1 test(s)
HELD    line 261  {env_file} was replaced between the checks      by 1 test(s)
HELD    line 274  {env_file} has {links} hard links               by 1 test(s)
UNHELD  line 108  could not restrict {path} to {user} alone
UNHELD  line 247  {env_file} is a symbolic link (kernel's ELOOP)
UNHELD  line 252  cannot write {env_file}
UNHELD  line 448  raise SystemExit(main())

held 6/10, unheld 4          file restored byte-identical: True
```

Line 448 is the `if __name__ == "__main__"` guard — a `raise` by grammar, not a refusal. The sweep
counted it because it counts honestly; reporting it as a finding would have been reporting the
probe rather than the repository.

## The measurement

`getpass.getuser()` on Windows is `USERNAME` from the environment, so an account name that does not
resolve makes the **real** `icacls` call fail for the real reason it would under a service account.
No mock anywhere in this measurement:

```
icacls exit 1332: nosuchaccount_hawedit: No mapping between account names and security IDs was done.
```

Against a directory granting `Everyone:(OI)(CI)F` — what a file inherits when nothing narrows it:

| | guard as committed | guard deleted (the sweep's UNHELD) |
|---|---|---|
| `write_credential` | **REFUSED** | **RETURNED** the path |
| file on disk | 95 bytes | 95 bytes |
| key in plaintext on disk | **True** | **True** |
| principals with access | Everyone, Administrators, SYSTEM, OWNER RIGHTS | same |
| readable by Everyone | **True** | **True** |

The guard's entire contribution was the exception. The exposure was identical either way, and
`main()` prints `✗ {exc}` and returns 2 — so the operator reads "nothing was stored" while a
readable key sits in their config directory.

## Why the order was wrong, and only on Windows

The comment above the `os.open` call is right about POSIX: *"A file cannot be created wider than
the mode passed here, so there is no window to lose."* On Windows the mode argument carries only
the read-only bit — measured earlier at D-113's follow-up, the file lands at `0o666` and inherits
the directory's ACL — so `restrict_to_owner` rebuilds the guarantee with `icacls`. Everything
between `os.open` and that call is therefore a window on Windows and nothing on POSIX, and the
key was written inside it.

**The fix is the order.** `restrict_to_owner` moves above the write, and deliberately above
`os.ftruncate` as well, for the same reason the code already declines `O_TRUNC`: a refusal that
happens after truncation destroys the previous credential on its way out, leaving the operator
with neither key.

```python
try:
    restrict_to_owner(env_file)
except (CredentialError, OSError):
    os.close(handle)
    raise

with os.fdopen(handle, "w", encoding="utf-8") as stream:
    os.ftruncate(stream.fileno(), 0)  # safe now: this inode is ours alone
    stream.write(body)
```

Re-measured, same real `icacls` failure, with a previous key already in the file:

```
--- icacls FAILS (unresolvable principal) ---
write_credential REFUSED: could not restrict …\.env to nosuchaccount_hawedit alone (icacls exited 1332)
new key in plaintext on disk : False
previous key still on disk   : True

--- control: icacls succeeds (real account) ---
write_credential RETURNED
new key in plaintext on disk : True
principals with access       : ['HAWAPC01\\Wareen']
readable by Everyone         : False
```

The control matters twice over: it proves the reorder did not break the mechanism. `icacls`
rewrites the DACL of a file this process holds open for writing, and the write still lands and
still comes out owner-only.

## The platform seam

`restrict_to_owner` returned early on `os.name != "nt"`, so its refusal is a branch **CI can never
execute** — the runner is Linux, and the machine that will hold the real key is Windows. The guard
protecting the important host was the one the grading host could not reach.

`_IS_WINDOWS` is now a module constant, and the test patches it rather than being skipped on POSIX.
That is not a new idea here: `_O_NOFOLLOW` is patched to `0` for exactly this reason, after the
gate refused a commit whose test skipped — *"a skip condition is creeping"* — and D-095's floor
compares `passed`, never `collected`, precisely so that a guard only one platform exercises cannot
be counted as covered.

Lines 247 and 252 are the same shape from the other side: on this Windows host `_O_NOFOLLOW` is 0,
so the pre-open check answers first and the kernel's `ELOOP` arm is unreachable — while on the
POSIX runner it is the live path that the symlink test actually drives. Unheld *here*, held
*there*, and now held on both by supplying the kernel's answer instead of waiting for it.

## Mutation audit — 5/5

```
baseline: GREEN (1626 passed, 86 warnings in 175.63s)

CAUGHT   the narrowing moves back below the write, as it was
         by 1: test_the_key_never_reaches_the_disk_when_the_narrowing_fails
CAUGHT   a failed icacls stops being a refusal
         by 1: test_a_narrowing_that_could_not_be_applied_is_refused_not_warned_about
CAUGHT   the kernel's ELOOP stops being reported as a symlink
         by 1: test_the_kernels_own_answer_about_a_symlink_is_a_refusal_too[10062-symbolic link]
CAUGHT   an unopenable env file stops being reported at all
         by 1: test_the_kernels_own_answer_about_a_symlink_is_a_refusal_too[13-cannot write]
CAUGHT   the platform switch claims this is not Windows
         by 4: test_a_permissive_environment_cannot_widen_the_credential_file,
               test_an_existing_permissive_file_is_tightened,
               test_the_key_is_never_world_readable_even_briefly, …

file restored byte-identical: True
5/5 caught
suite after restore: GREEN
```

Each new test carries a control that fails for the plausible wrong answer: the ordering test writes
the key successfully once the narrowing is restored (otherwise it would pass against a
`write_credential` that never writes at all), and the `icacls` test returns normally on exit 0
(otherwise it would pass against any intercepted subprocess call).

**The fifth mutation is honest but weaker than it looks.** `_IS_WINDOWS: Final = False` is caught by
four tests *on this host*; on the Linux runner that is already the value, so the mutation is a
no-op there and those four tests are measuring the POSIX branch either way. It is recorded as
caught because it was, on the machine where the constant means something.

## A filter lied again, and this one was mine

The first audit run died with `IndexError` looking for the `N passed` line. `pyproject.toml`'s
`addopts` already carries `-q`, so passing `-q` again makes it `-qq` — which suppresses the count
line entirely. The earlier sweep printed a pytest documentation URL as its "baseline: GREEN (…)"
summary for the same reason and I read past it. Both harnesses now take green from the **exit
code** and print the count only if there is one.
