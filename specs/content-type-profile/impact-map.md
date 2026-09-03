# Impact Map: Content-Type Profiles (Task T4.5, ADR D-265)

## 1. Target Symbols & Callers

### New Module `src/hawedit/content_type.py`
- `ContentType(str, Enum)`
- `ContentTypeProfile` (dataclass)
- `CONTENT_TYPE_PROFILES: Final[dict[ContentType, ContentTypeProfile]]`
- `DEFAULT_CONTENT_TYPE: Final[ContentType]`
- `get_content_type_profile(content_type: ContentType | str | None) -> ContentTypeProfile`

### Modified Module `src/hawedit/pipeline.py`
- Import `ContentType`, `ContentTypeProfile`, `get_content_type_profile`.
- `build_parser`: Add `--content-type` argument with choices `[c.value for c in ContentType]`, default `"podcast"`.
- `run_pipeline`:
  - Accept `content_type: ContentType | str = ContentType.PODCAST`.
  - Resolve `profile = get_content_type_profile(content_type)`.
  - Apply profile defaults to `min_clip_ms`, `caption_style`, `punch_in_cadence`, `eased_push`.
- `main`: Forward `content_type=args.content_type`.

### New / Modified Test Modules
- New test module: `tests/test_content_type.py`:
  - `test_content_type_enum_members_and_string_values`
  - `test_get_content_type_profile_returns_canonical_profiles`
  - `test_get_content_type_profile_defaults_to_podcast_on_none`
  - `test_get_content_type_profile_raises_on_unknown_string`
  - `test_news_profile_disables_punch_ins_and_eased_push`
  - `test_social_profile_uses_word_highlight_and_fast_cadence`
- `tests/test_pipeline.py`:
  - `test_pipeline_content_type_argument_is_parsed`
  - `test_run_pipeline_respects_content_type_defaults`

## 2. Risk Assessment
- Default remains `podcast`, preserving 100% exact fidelity for existing ep29 pipeline runs and golden tests.
- Zero new external dependencies.
