# Plan — runtime composition reconciliation

Approved-by: Hawa, 2026-08-15 (approved full implementation plan)

1. Add a failing live-VEX test that replaces the imported shared prefix with a sentinel and
   proves command construction consumes it; update setup tests to require the public name.
2. Export `wsl_prefix`, migrate setup and Stage 1, delete the VEX duplicate, and migrate all VEX
   invocations.
3. Run the focused WSL/ASR/VEX plus ASR/frame/device/lifecycle regression set.
4. Recompute and review the package digest; rebind the VEX policy without inheriting live
   acceptance, using the required self-edit marker.
5. Run the canonical committed-tree gate, ratchet only through the gate, push a draft PR, and
   require exact-SHA hosted CI before merge.
