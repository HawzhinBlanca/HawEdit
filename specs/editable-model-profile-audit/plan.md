# Plan — editable model-profile audit

Approved-by: Hawa, 2026-08-15 (approved full implementation plan)

1. Add failing tests that model one authoritative PEP 660 HawEdit distribution whose checkout
   lock is present but whose editable RECORD contains no wheel data-file entry.
2. Add refusal tests for edited lock bytes, manifest drift, wrong editable root, and preserve
   the existing wheel RECORD/tamper tests.
3. Implement one authoritative editable-versus-wheel branch inside
   `audit_installed_profile()`, reusing existing root/manifest/lock validators.
4. Run focused tests and strict type/lint checks.
5. Reinstall HawEdit editable in the real dedicated model-fetch environment and prove the
   production preflight succeeds without network or a wheel substitution.
6. Run the canonical gate from a committed clean source tree; commit exact paths, push a draft
   PR, and require hosted exact-SHA CI before merge.
