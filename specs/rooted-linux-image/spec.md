# Rooted Image EARS

Proposed requirements; tests below are planned, NOT implemented or passed.

| ID | Requirement | Named regression |
| --- | --- | --- |
| R1 | WHEN rooted image preparation is explicitly selected, THE snapshot SHALL independently copy every declared byte and verify an immutable original-description-bound process root before returning. | test_rooted_image_original_root_and_readonly_kernel_state |
| R2 | WHEN a consumer normalizes its path and outside parents are renamed/replaced, THE admitted image SHALL keep that consumer inside the original copied tree or refuse before foreign bytes are consumed. | test_rooted_image_normalised_elf_consumer_survives_parent_replacement; test_rooted_image_genuine_transformers_consumer (T2) |
| R3 | WHEN executable permission is requested, THE snapshot SHALL accept only explicit typed declarations in rooted mode and preserve exact copied hashes/regular-single-link invariants. | test_rooted_image_executable_declaration_refusals |
| R4 | WHEN proc names collide, initializer ABI is unavailable, transition/root readback fails or original custody changes, THE snapshot SHALL refuse irreversibly and require original scope drain. | test_rooted_image_reserved_proc_refuses; test_rooted_image_original_root_substitution_refuses |
| R5 | WHEN image byte/count bounds are malformed or exceeded, THE snapshot SHALL refuse before preparing the mount and SHALL keep existing data-only/default/per-file bounds. | test_rooted_image_capacity_and_default_bounds |
| R6 | WHEN initialization succeeds, THE snapshot SHALL retain zero capability sets, NoNewPrivs, original descriptor/namespace ownership and inherited namespace-reentry refusal. | test_rooted_image_reentry_thread_and_fork_refuse; existing test_linux_snapshot_fence_and_inheritance |
| R7 | WHEN a real model consumer is released, THE protected producer SHALL require complete owned executable/library/source/model/input closure, reserved resources and actual original controller/member lifetime, not receipt flags. | test_rooted_image_complete_runtime_consumer (T2); test_rooted_producer_owned_closure_release (T3) |
| R8 | WHEN input/runtime/review/security/billing or publication authority is uncertain, THE studio SHALL refuse or reconcile without completing/publishing a deliverable. | test_rooted_producer_uncertain_authority_refuses_publication (T3), plus existing studio authority/billing/review/export controls |
| R9 | WHEN a native runtime retains a read-only executable file description, THE rooted image SHALL require exact declared bytes and original-description custody, replace it with the verified private copy preserving its offset, and refuse writable/inheritable/undeclared/reopened handles without closing foreign descriptions. | test_rooted_image_retained_runtime_description_and_callbacks; test_rooted_image_retained_same_inode_new_description_refuses; test_rooted_image_retained_runtime_refusals; test_rooted_image_outside_descriptions_refuse |

R7/R8 and original seven-phase/AC1--AC12 obligations remain full-system exit
requirements; no T1 component pass may substitute for them. Every new behavior
gets an actual named automated regression before implementation.
