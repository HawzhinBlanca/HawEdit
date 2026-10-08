# EARS

1. WHEN a nonempty width request has an unavailable or failed renderer, THE caption
   system SHALL refuse without estimating or caching a successful measurement.
   Tests: test_caption_width_missing_renderer_refuses_without_poisoning_cache,
   test_caption_width_failed_renderer_refuses_after_a_valid_cache_entry.
2. WHEN decoded pixels do not match the requested extent, THE caption system SHALL
   refuse without retaining a width. Test: test_caption_width_rejects_invalid_decoded_extent.
3. WHEN actual renderer/fonts/canvas context differs, THE caption system SHALL not
   reuse a prior-context width and SHALL refuse observed resource drift.
   Tests: test_caption_width_cache_binds_renderer_fonts_and_canvas,
   test_caption_width_changed_font_context_remeasures.
4. WHEN pixel-limited lines/popups are built, THE caption system SHALL measure with
   the selected font name/size/directory and canvas in every applicable style branch.
   Tests: test_ass_pixel_wrapping_uses_selected_font_size,
   test_ass_popup_width_uses_selected_font_context,
   test_ass_generic_popup_width_uses_selected_font_size,
   test_ass_pixel_measurement_refuses_unavailable_selected_font,
   test_ass_pixel_measurement_refuses_empty_selected_fonts,
   test_ass_pixel_measurement_uses_selected_canvas_height,
   test_direct_pixel_consumers_use_selected_font_size,
   test_rtl_positions_measure_selected_canvas_height.
5. WHEN char-only captions/SRT are built, THE caption system SHALL preserve original
   text/timing/order and unbroken long-word behavior. Existing whole caption/delivery
   modules and golden references remain unchanged.
   Test: test_char_only_consumers_do_not_require_render_resources.

Measurements do not authenticate editorial meaning, publication or release.
