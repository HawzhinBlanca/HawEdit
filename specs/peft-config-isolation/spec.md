# EARS Specification

1. WHEN a champion is assembled, THE backend SHALL load the held adapter JSON,
   register the original Fairseq2 Linear mapping on that config instance, and
   pass that exact instance to PEFT without changing its shared constructor.
   Test: test_champion_consumers_receive_held_assets.
2. WHEN config parsing, PEFT loading or pipeline assembly fails, THE backend
   SHALL propagate failure without changing the shared PEFT constructor or
   registering unrelated later configuration instances.
   Test: test_champion_config_failure_does_not_change_shared_constructor.
3. WHEN the pinned real champion is loaded, THE backend SHALL preserve the saved
   LoRA parameters at the existing dtype conversion and decode the same real
   development audio without changing model policy.
   Test: test_champion_consumers_receive_held_assets (assembly arguments);
   additionally require the source-current real tensor/development check,
   separate from accuracy and holdout acceptance.

BLUEPRINT sections 4.1/7; D-181, D-285, D-286. No human fidelity, speed,
publication or qualified security approval is implied by loader correctness.
