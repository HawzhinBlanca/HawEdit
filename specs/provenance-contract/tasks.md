# Tasks — Provenance in the Contract (`specs/provenance-contract`)

- [ ] T1 Define `Provenance` dataclass, bind to `Clip`, update `to_dict()`/`from_dict()`, and enforce in `Clip.assert_renderable()`
- [ ] T2 Enforce Clause 9 (FFmpeg version agreement) in `reconcile_delivery` in `src/hawedit/delivery.py`
- [ ] T3 Add tests `test_a_contract_names_every_constant_that_shaped_it`, `test_render_gate_refuses_clip_without_provenance`, and `test_delivery_refuses_ffmpeg_version_mismatch`
