# Impact map — credentials panel

## `Download` (Protocol) — `model_fetch.py:91` — **gains `token: str | None`**

| caller | site | covered by |
|---|---|---|
| `_download_client` returns `snapshot_download` | `model_fetch.py:529` | `tests/test_model_fetch.py` client-drift tests |
| `fetch_checkpoint(item, store, download)` | `model_fetch.py:341` | `tests/test_model_fetch.py` fetch suite |
| test stubs implementing `Download` | `tests/test_model_fetch.py` | themselves |

Every stub must gain the parameter or fail `mypy --strict`. This is the whole reason the
protocol change is its own task: it is a typed contract with several implementations, and a
keyword-only argument with a `None` default keeps each caller working.

## `main` — `credentials.py:463` — **unchanged**

The terminal panel stays exactly as it is and becomes the headless fallback (AC-2). Not
rewritten: it is the audited path, and a GUI that replaces rather than fronts it would move the
secret handling into new code for no reason.

| caller | site | covered by |
|---|---|---|
| `hawedit-credentials` console script | `pyproject.toml:119` | `tests/test_credentials.py` |

## `write_credential` / `read_credential` — `credentials.py:193,155` — **unchanged**

Already generic by name; storing a second credential needs no change. Widely covered by
`tests/test_credentials.py`. **No signature change, so no caller is affected.**

## New: `src/hawedit/setup_panel.py`, `hawedit-setup` console script

No callers yet. tkinter is imported *inside* the launch function so `credentials.py`'s import
path — which `pipeline.py` sits on — never pulls Tk.

## Gap found

`model_fetch.py:634` is the only reader of `HF_TOKEN` in the codebase and it reads
`os.environ` directly. There is no test asserting a *stored* token is honoured, because until
now none could be. T2 adds one.
