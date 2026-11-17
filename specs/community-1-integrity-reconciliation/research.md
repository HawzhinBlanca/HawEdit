# Community-1 Pinned Integrity Research

2026-10-14, baseline49d36f923a154d38a1f96cb72540aabd98f6f58d.
Owner explicitly approves downloading the existing selected Community-1 weights
through the pinned fetcher, after canonical verification. That gate finished
6400pass/1VEX failure; the subsequent exact fetch command refused before download.

The checked-in models/integrity.json row still records five redacted LFS hashes.
Authenticated read-only Hub API access now returns those five exact hashes at
3533c8cf8e369892e6b79ff1bf80f7b0286a54ee, matching models/revisions.json. All ten
paths, sizes and five regular Git blob identities match the existing row. This
resolves the old remote-metadata uncertainty, not the download or runtime checks.

Raw authenticated metadata (no token in output):
`C:/Users/Wareen/HawEditCommunity1-pinned-metadata-stdlib-20261014.json`,
SHA2566ac8aa93d5fa0a9435612d466b72f3b4e8a9cb3be6aa5528453f3474f7e9d956.
Endpoint: https://huggingface.co/api/models/pyannote/speaker-diarization-community-1/revision/3533c8cf8e369892e6b79ff1bf80f7b0286a54ee?blobs=true
Read via existing Python urllib with saved HF_TOKEN; no terms accepted or weights
executed. The earlier optional HfApi read refused because the Windows host lacks
huggingface_hub; raw failure retained separately. Existing WSL SDK metadata reports
exact huggingface_hub0.36.2, matching DOWNLOAD_CLIENT_VERSION, without importing
the SDK or models. Its full models profile/download transport is not yet audited.

| Pinned File | SHA256 |
| --- | --- |
| diarization.gif | 0d925ad38995d89009260e493b0ae2e684c3e1397f495265ed841c45c4f73a35 |
| embedding/pytorch_model.bin | 6f10ff60898a1d185fa22e1d11e0bfa8a92efec811f11bca48cb8cafebefd929 |
| plda/plda.npz | 9b77bcd840692710dd3496f62ecfeed8d8e5f002fd991b785079b244eab7d255 |
| plda/xvec_transform.npz | 325f1ce8e48f7e55e9c8aa47e05d2766b7c48c4b25b8de8dd751e7a4cc5fbe8f |
| segmentation/pytorch_model.bin | 7ad24338d844fb95985486eb1a464e32d229f6d7a03c9abe60f978bacf3f816e |

AGENTS prohibits models/integrity.json edits; download approval does not explicitly
lift that separate boundary. Do not silently edit it, substitute external custom
metadata or invent hashes. BLUEPRINT sections3/7/8.1, BLOCKED #4/#24 and the existing
verified atomic fetch/publication policy remain authoritative.
