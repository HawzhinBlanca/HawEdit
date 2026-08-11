# The panel branch that prints a stored key, driven by no test

`credentials.py` opens by saying *"an error message containing a credential is how secrets reach
log aggregators"*, and M2.8's cell claims the panel *"never prints it"*. Four ways a key could
escape, mutated one at a time against a baseline verified green first:

```
CAUGHT    the key moves from the header into the URL query string
            tests/test_credentials.py::test_key_validation_authenticates_by_header_never_by_url
SURVIVED  the panel prints the key instead of the mask
CAUGHT    mask hands back the whole secret
            test_masking_shows_enough_to_tell_two_keys_apart_and_no_more
            test_the_panel_prints_the_mask_and_never_the_key
CAUGHT    an unreachable API reports the key alongside the error
            test_an_unreachable_api_message_does_not_contain_the_key

3/4 caught by the suite as it stands
```

The surrounding surface is well guarded — the API-key **header** (so the credential cannot leak
through URL logging, proxies or exception traces), the mask, and the unreachable-API message all
have their own tests.

## Why the survivor survived

`test_the_panel_prints_the_mask_and_never_the_key` exists and is not weak — it asserts both
`FAKE_KEY not in accepted` and `mask(FAKE_KEY) in accepted`. It drives the **entry** path, where
the key arrives from `getpass`.

The line that survived is on the **status** path:

```python
key, check = credential_status()
if key is None:
    print(f"{GEMINI_API_KEY}: not set")
else:
    source = "environment" if os.environ.get(GEMINI_API_KEY) else "user config"
    print(f"{GEMINI_API_KEY}: {mask(key)}  (from {source})")
```

`_drive_main` stubs the validator, the writer and `getpass` — but not `credential_status`. On a
machine with no key configured that returns `None`, so **the `else` branch executes in no test at
all**. It is the branch every user with a key stored hits on every run of `hawedit-credentials`,
and the one whose output lands in terminal scrollback.

`--check`, the scriptable path most likely to be piped into a log, was driven by no test either.

## The guards

`test_the_status_readout_for_a_stored_key_never_prints_it` and
`test_check_reports_a_stored_key_without_printing_it` run the real `main()` with
`credential_status` returning a stored key. Each asserts the key is **absent** and the mask is
**present** — the second half being the control, without which both pass for a panel that prints
nothing and "never prints it" becomes true by silence. The `--check` test also asserts both exit
codes, since "reports status" is only true if a good key and a rejected one differ.

## Mutation audit — 3/4 lint-clean

```
CAUGHT  the survivor restored: the readout prints the key   <- ONLY the new guards
            test_check_reports_a_stored_key_without_printing_it
            test_the_status_readout_for_a_stored_key_never_prints_it
CAUGHT  --check reports success whatever the API said       <- ONLY the new guards
            test_check_reports_a_stored_key_without_printing_it
CAUGHT  the mask leaks the whole secret                     (4 tests, two pre-existing)
CAUGHT  the readout prints nothing at all                   [LINT/FORMAT DIRTY — not counted]

3/4 caught lint-clean
```

**Two mutations are caught by the new guards and nothing else**, and the second was not what this
iteration set out to find: `--check` returning 0 regardless of what the API said means a script
gating on `hawedit-credentials --check` would proceed with a revoked key. That is the whole
purpose of the flag.

The vacuity mutation reddened the new guards too, but its replacement left the block
format-dirty, so it measured ruff as well and is not counted (D-148, D-150). The non-vacuity it
was testing is established inside the guards themselves by the `mask(...) in out` assertion.

**No production code changed.** Every path was already correct; two of them were accountable to
nothing.
