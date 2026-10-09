# EARS

| ID | Requirement | Named Test |
|---|---|---|
| W1 | WHEN encoding fails, THE worker SHALL refuse without reserving an empty final result. | test_worker_encoding_failure_does_not_publish_empty_output |
| W2 | WHEN a final name is occupied, THE worker SHALL preserve it and refuse before production model construction/inference. | test_worker_existing_output_refuses_before_backend,test_worker_existing_output_directory_refuses_before_backend |
| W3 | WHEN an original child is terminated, THE final result SHALL be absent or complete, never partially streamed. | test_worker_public_name_is_complete_before_original_child_termination |
| W4 | WHEN publication succeeds, THE transfer SHALL preserve exact JSON/schema/origins/text/clocks, UTF8bytes and LF. | test_worker_result_preserves_exact_utf8_and_newline,test_worker_publication_preserves_sorani_utf8_bytes |
| W5 | WHEN admitted writers race, THE worker SHALL publish one complete result without overwriting the winner. | test_worker_concurrent_result_publication_has_one_unchanged_winner |
| W6 | WHEN cleanup runs, THE worker SHALL remove only its own staging file and preserve unrelated retained evidence. | test_worker_does_not_remove_unrelated_staging_evidence |

This is a write-once worker transfer, not canonical result reuse/retry authority,
directory-fsync/power-loss durability, GPU/effect reconciliation, authentic
review, published delivery, real speech accuracy or security acceptance.
