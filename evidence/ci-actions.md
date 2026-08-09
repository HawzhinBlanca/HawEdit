# GitHub Actions source identity — 2026-08-09

The gate previously executed moving major-version tags. The official action repositories were
queried and the release tags resolved to immutable commits as follows:

| Action tag | Full commit used by the workflow |
|---|---|
| `actions/checkout@v7.0.1` | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/setup-python@v7.0.0` | `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| `actions/attest@v4.1.1` | `a1948c3f048ba23858d222213b7c278aabede763` |
| `actions/download-artifact@v8.0.1` | `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` |
| `actions/upload-artifact@v7.0.1` | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` |

`.github/workflows/gate.yml` and `.github/workflows/release.yml` use the commits while keeping the
tag names in comments for human update context. `tests/test_fetch_scripts.py` scans every workflow and refuses any remote
`uses:` target that is not a full 40-hex commit. Local actions and `docker://` images are treated
separately because they do not have this `owner/repo@commit` form.

## Node runtime audit

Exact-SHA gate run 31291508018 succeeded but GitHub annotated both former commits: their actions
targeted deprecated Node 20 and the runner was force-executing them on Node 24. A full commit pin
therefore proved source identity while still depending on compatibility emulation.

The official `action.yml` at Checkout 7.0.1, Setup Python 7.0.0, Attest 4.1.1, Download Artifact
8.0.1 and Upload Artifact 7.0.1 was read through the GitHub API; all five declare
`runs.using: node24`. The release pages and immutable tag objects are:

- <https://github.com/actions/checkout/releases/tag/v7.0.1>
- <https://github.com/actions/setup-python/releases/tag/v7.0.0>
- <https://github.com/actions/attest/releases/tag/v4.1.1>
- <https://github.com/actions/download-artifact/releases/tag/v8.0.1>
- <https://github.com/actions/upload-artifact/releases/tag/v7.0.1>

The new regression requires these two audited commit/tag pairs in addition to the generic full-SHA
rule, so rolling back to a pinned Node-20 action is red. The first workflow-dispatch run after this
change remains the runtime evidence that GitHub can fetch and execute the commits; a local YAML
assertion alone cannot prove that.

Runtime result: workflow-dispatch run
<https://github.com/HawzhinBlanca/HawEdit/actions/runs/31291847181> executed exact source SHA
`32ba77bfdd95376b5404fa85257d6a5d9f841595`, completed every gate and real-media post-check, and
returned **zero check-run annotations**. The former Node-20 deprecation annotation is absent.
