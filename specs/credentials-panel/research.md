# research — credentials panel (operator tool)

Goal: one window where Hawa pastes two tokens and sees what each unlocks. She is not a
programmer; `getpass` in a terminal is the current front door and it only handles one of them.

## What exists
| symbol | file | state |
|---|---|---|
| `write_credential(name, value, ...)` | `credentials.py:193` | **already generic by name**. O_NOFOLLOW, mode 0600 at creation, `icacls` ACL on Windows, refuses a non-git-ignored path |
| `read_credential(name, env_file)` | `credentials.py:155` | env first, then the owner-only user config |
| `ENV_FILE` | `credentials.py:70` | `%APPDATA%/hawedit/credentials.env` — outside the checkout, cannot be committed |
| `validate_gemini_key` | `credentials.py:390` | live check against Google, bounded response, header-safe key check |
| `credential_status` | `credentials.py:446` | `(key, KeyCheck | None)` |
| `main` | `credentials.py:463` | terminal panel, `getpass`, **GEMINI_API_KEY only** |
| `mask` | `credentials.py:134` | the only way a secret is ever displayed |

## The gaps
1. **`HF_TOKEN` is not a stored credential at all.** Only `model_fetch.py:634` reads it, and it
   reads `os.environ` directly — so a token in the credential store would be invisible.
2. **`snapshot_download` never receives a token.** The `Download` protocol
   (`model_fetch.py:91`) has `repo_id/revision/local_dir/resume_download` and no `token`, so the
   gated fetch depends entirely on `huggingface_hub` finding `HF_TOKEN` in the ambient
   environment. Storing it without fixing this changes nothing.
3. **No HF token validation** exists to mirror `validate_gemini_key`.

## Terrain
- `tkinter` is **stdlib** and present here (Tcl/Tk 8.6, py3.12.10). No new dependency, so no ADR
  is owed on that count — D-002's licence gate is not engaged.
- `credentials.py` is imported by `pipeline.py`; a tkinter import must not land in that path, so
  the panel belongs in its own module.
- §7's gated row is `pyannote/speaker-diarization-community-1` (`registry.py:179`), whose
  download is what `HF_TOKEN` unlocks — `BLOCKED.md` **#4**.
- `GEMINI_API_KEY` unlocks §3 Stage 3 Path A and Stage 4. Note `gemini-2.5-pro`'s free tier is
  zero, so a valid key still needs billing — `BLOCKED.md` **#3**.

## Risks
- A GUI that cannot open (headless, no display) must degrade to the existing terminal prompts,
  not crash. `tkinter.TclError` is the signal.
- Secrets must never reach a log, a window title, a traceback, or `git`. Only `mask()` output is
  displayable.
- Changing the `Download` protocol touches every test stub that implements it — impact-map lists
  them.

## Answers to
§3 Stage 0 / Stage 3 / Stage 4 provisioning · `BLOCKED.md` **#3** and **#4** · D-002 (no new
dependency engaged).
