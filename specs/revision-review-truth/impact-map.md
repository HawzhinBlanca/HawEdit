# Actual Caller Impact

Fresh original structured Serena map/hash in research.md; paths and raw source
locations retained there. LSP absence is not proof dynamic dispatch is unused.

| Symbol | References | Affected Production Callers | Caller Tests |
| --- | --- | --- | --- |
| propose_render | 19 | _main_render; render_agent.build_render_agent/propose_render_tool | test_exploration_tools; test_explorer_agent; test_prompt_injection; real boundary proposal |
| render_boundary_revision | 26 | commit_render; _main_boundary | test_proposals; test_exploration_tools; test_render_boundary_revision |
| render_caption_revision | 22 | commit_render; _main_caption | test_proposals; test_render_caption_revision |

_refuse_existing_revision_artifacts has2renderer consumers, reused unchanged
with an added proposal caller. _claim_revision_render has2renderer consumers,
unchanged. commit_render6references, public signature/decision behavior unchanged.
Mapped render_clip65references/Clip.assert_renderable35references, unchanged;
pipeline/publication/cache callers retain their real gates. Both real_run fixtures
have no static refs because pytest resolves them dynamically; reuse unchanged.
New test functions in both real-render modules use private copies of original
reports, not changes to shared fixture output or golden bytes.
