# Proposed outcome acceptance criteria

Date: 2026-09-09. Approved-by: pending for new scope. Test names below are proposals, not existing or passing test evidence. Automated assertions support but do not replace independent human editorial evaluation under BLUEPRINT §8.

| ID | EARS criterion | Proposed automated evidence |
|---|---|---|
| CD-01 | WHEN no source media has been registered, THE application SHALL refuse generation and SHALL NOT report completed output. | `test_director_ui_requires_registered_media` |
| CD-02 | WHEN the rendered media is absent, changed or unreadable, THE critic SHALL refuse an all-clear verdict. | `test_director_critic_rejects_missing_changed_and_undecodable_media` |
| CD-03 | WHEN inspection does not obtain actual pixels or audio for an interval, THE report SHALL mark that interval uninspected. | `test_director_coverage_counts_observed_media_only` |
| CD-04 | WHEN an episode contains an eligible highlight near its end, THE discovery stage SHALL consider it before applying the output quota. | `test_director_discovers_late_episode_gold_moment` |
| CD-05 | WHEN a selected statement depends on omitted context, THE planner SHALL include sufficient context or reject the candidate. | `test_director_keeps_referent_qualification_and_causal_dependencies` |
| CD-06 | WHEN a pause-derived segment ends with an unresolved dependent clause, THE editor SHALL NOT accept it as a completed thought. | `test_director_rejects_pause_complete_but_semantically_open_ending` |
| CD-07 | WHEN speech is pruned, THE output SHALL preserve the source claim's negation, attribution, qualification and chronology. | `test_director_pruning_preserves_meaning_critical_words` |
| CD-08 | WHEN a short input contains removable verbal waste, THE system SHALL assess that waste even when the input is under maximum duration. | `test_director_short_input_receives_contextual_pruning` |
| CD-09 | WHEN retained source intervals are joined, THE rendered speech, captions and sidecars SHALL follow the same ordered source-time mapping. | `test_director_splices_preserve_media_and_caption_clock` |
| CD-10 | WHEN the source changes camera, THE renderer SHALL preserve the intended person or an explicitly justified source composition throughout the accepted shot. | `test_director_source_cut_cannot_publish_table_in_place_of_speaker` |
| CD-11 | WHEN the intended crop loses required content, THE final inspection SHALL detect the loss from rendered frames and block approval. | `test_director_output_critic_detects_real_crop_loss` |
| CD-12 | WHEN a highlights anthology is requested, THE planner SHALL select independently complete moments and SHALL NOT invent a causal relation between them. | `test_director_anthology_preserves_distinct_complete_moments` |
| CD-13 | WHEN a candidate is repaired, THE workflow SHALL invalidate previous approval and require fresh evidence for the new bytes within a bounded repair budget. | `test_director_repair_requires_fresh_evidence_and_stops_at_budget` |
| CD-14 | WHEN two different candidate outputs are shown, THE UI SHALL bind each title, duration, preview and download to its own verified plan and artifact identity. | `test_director_candidate_ui_matches_distinct_artifacts` |
| CD-15 | WHEN a source cannot produce a qualifying short, THE system SHALL report no qualifying output rather than force a filler clip. | `test_director_abstains_without_filling_quota` |
| CD-16 | WHEN a benchmark score is produced, THE evaluator SHALL account for all sources, candidates, refusals, ties and human intervention and SHALL reject contaminated or stale holdout evidence. | `test_director_scorecard_accounts_for_all_sources_and_interventions` |
| CD-17 | WHEN the final movie or plan changes after approval, THE delivery path SHALL invalidate that approval. | `test_director_publication_requires_exact_approved_artifacts` |
| CD-18 | WHEN a run is interrupted and resumed, THE UI SHALL recover real stage state without substituting a demo or stale output. | `test_director_resume_restores_source_bound_real_job` |

Use small deterministic tests for contracts and intentionally damaged real-media pairs for perception tests. Semantic tests need independent Sorani labels and include both valid and invalid alternatives. Do not fake perception by injecting the exact defect that the function is expected to return. Full-media acceptance must execute rather than disappear from collection when an environment variable is absent.
