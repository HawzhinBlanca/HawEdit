# Caller Impact

Actual Serena maps cited in research.md, not inferred signatures.

- commit_boundary_revision:27refs; CLI _main_boundary, tests/test_proposals.py,
  test_render_boundary_revision.py and test_exploration_tools.py.
- commit_caption_revision:12refs; CLI _main_caption, test_proposals.py and
  test_render_caption_revision.py.
- render_boundary_revision:21refs; commit_render and CLI _main_boundary;
  test_proposals.py, test_render_boundary_revision.py, test_exploration_tools.py.
- render_caption_revision:17refs; commit_render and CLI _main_caption;
  test_proposals.py and test_render_caption_revision.py.
- propose_render19refs and commit_render6refs remain consumers of stored
  revision status. Failed/conflicting partial output cannot become rendered.
- render_clip65refs: retain signature and its existing no-replace MP4 publisher.
  Do not move cleanup of final artifacts into this renderer or weaken caption,
  boundary, measurement or publication guards.
- Generic atomic_fs.write_text_atomic22refs and directory publisher26refs are
  mapped but not changed. Revision-only text publication uses the existing
  same-directory hard-link no-replace pattern with owned unique staging.
- Authenticated candidate review6refs, retained cache2refs, studio inspection
  2refs remain unchanged. This unit grants no publication/HTTP authority.
- Historical overwrite regression has no callers; preserve its exact name and
  replace overwrite assertions with stricter refusal plus byte preservation.

Full raw caller paths/names remain in structured maps. Existing editor/render/
learning and exploration tests join the revision suites for affected verification.

Current helper/render5pair mapac25d980727a7ac9371d317fef165660004a4c3dc80045cac05fc15db8c244d9
adds actual original-record claim adoption, unchanged mapper source/ref/status.
Final helper/test6pair mapc94cbf8f9a7501980029ee2116449d48826355cfc6fbce631718d31516072090
precedes manual SIM117 context-format correction. New MP4 collision tests have
no callers; staging has both render/text consumers, publisher has commits,
sidecars and claim consumer, claim/refusal have both render consumers. Full raw
details in C:/Users/Wareen/HawEditRevisionFormatContracts-20261009/serena-map.json.
Original mapper gone/session31544closed. No production fixture/golden changes.
