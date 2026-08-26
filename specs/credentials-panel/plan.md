# Plan — credentials panel

## Approach

One window, two masked fields, a Verify & Save button each, and a line under each saying what it
unlocks. `tkinter` is stdlib and already present (Tcl/Tk 8.6), so **no dependency is added and
no ADR is owed on that count**.

**The GUI fronts the audited path; it does not replace it.** `write_credential`
(`credentials.py:193`) already opens with `O_NOFOLLOW`, creates at mode 0600 so there is no
window where the file is world-readable, rewrites the Windows ACL to owner-only, and refuses a
target git could track. That code is not touched. The panel collects a string and hands it to
the same function the terminal panel does.

**Secrets are never displayed, logged, or put in a window title** — only `mask()` output, which
is the existing rule (`credentials.py:134`).

**Storing `HF_TOKEN` is useless without the second half.** `snapshot_download` currently gets no
token, so the gated fetch depends on `huggingface_hub` finding `HF_TOKEN` in the ambient
environment. Adding the credential without adding `token=` to the `Download` protocol would be a
feature that silently does nothing — the exact failure mode this repo keeps finding. T2 is that
fix and comes before the GUI.

## Files and symbols

| file | change |
|---|---|
| `src/hawedit/credentials.py` | `HF_TOKEN` constant, `validate_hf_token`, extend `credential_status` |
| `src/hawedit/model_fetch.py` | `Download` protocol gains `token`; read via `read_credential` |
| `src/hawedit/setup_panel.py` | **new** — tkinter panel, terminal fallback |
| `pyproject.toml` | `hawedit-setup` console script |
| `tests/test_credentials.py`, `tests/test_model_fetch.py`, `tests/test_setup_panel.py` | tests |

## Divergence from BLUEPRINT
None. This is operator tooling for provisioning §7 already specifies.

## Risks
- **This clears no blocker by itself.** It makes `BLOCKED.md` #3 and #4 *answerable* by Hawa in
  one window. #4 still needs her to accept the licence on the repo page; #3 still needs billing.
- A headless machine must fall back, not crash (AC-2). Tk raises `TclError` on `Tk()`; that is
  the branch.
- The `Download` protocol change touches every test stub implementing it — impact-map lists them.
  A keyword-only `token` defaulting to `None` keeps each one working.

## What this does NOT do
It does not make the video better. It removes the reason two stages cannot run. Everything
downstream — real Stage 3/4 judging, real diarization — still has to be run and looked at
afterwards, and `diarization-adapter` T6 still cannot start until the weights actually download.

Approved-by: Hawa (in chat, 2026-08-26) - approved as designed, all four tasks.
