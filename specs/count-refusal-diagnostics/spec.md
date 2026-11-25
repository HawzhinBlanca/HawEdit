# EARS

CR1: WHEN policy expires at the actual pre-count egress fence, THE guard SHALL
preserve its expired refusal and send no upstream request or generation.
test_count_boundary_preserves_actual_policy_expiry.

CR2: WHEN native journal integrity fails at the pre-count fence, THE guard SHALL
preserve its storage refusal as a typed cause under the existing external count
error contract, name the journal failure, and send no upstream request or generation.
test_count_boundary_preserves_actual_storage_refusal.

CR3: WHEN a genuine count transport fails, THE guard SHALL retain the provider
unavailable diagnostic/cause and create no billed generation intent.
test_count_boundary_retains_actual_provider_failure.

CR4: WHEN generation has committed billed intent, THE guard SHALL preserve its
existing uncertainty/replay restrictions. Whole tests/test_studio_billing.py,
including test_studio_billing_response_loss_refuses_replay.
