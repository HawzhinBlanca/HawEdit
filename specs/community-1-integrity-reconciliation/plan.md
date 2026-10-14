# Pinned Community-1 Reconciliation Plan

Approved-by: Wareen, 2026-10-14, "approved the scoped reconciliation plan, including the integrity row exception. download Community-1 and continue fixing the protected GPU/ASR pipeline"

The already approved download is retained. This additional plan requests an
explicit exception for only the Community-1 row of models/integrity.json, which
AGENTS otherwise protects. No other model, revision, dependency, source policy,
licence, secret, VEX date/binding, golden/fixture or gate changes are authorized.

1. Repeat authenticated metadata at the exact existing pin, compare all paths,
   sizes and regular Git blob identities, and retain provenance. Map any source
   symbols before proposing source changes; this plan expects metadata only.
2. Under the explicit exception, replace only the five unavailable hash fields
   with measured SHA256 identities and replace the row's blocked status/reason
   using the existing integrity schema. Preserve all other model rows verbatim.
   Preserve test_gated_checkpoint_with_redacted_digests_is_refused_not_approximated
   with the same strict blocked/redacted assertion, selecting a real temporary
   manifest containing the historical blocked row instead of assuming current
   remote access remains denied. Add a separate measured verified-row regression.
   No mocked validator, assertion weakening, golden/fixture or harness change.
3. Verify an existing audited environment with the exact download client and
   required models profile. Reuse it only through secure original host transport
   and the existing pinned staged fetcher. If its profile fails, retain refusal;
   no package installation, environment spoofing or custom downloader bypass.
4. Fetch and independently verify the exact complete file set through existing
   ModelStore checks and atomic publication. Run exact bash scripts/verify.sh;
   record changed asset digest for qualified VEX review. No ledger promotion
   without required current gate and CI.

No model execution, unseen terms acceptance, paid inference, publication or
production readiness claim follows from successful provisioning.

Read-only follow-up2026-10-14: existing .venv-gpu on WindowsCPython3.11.15
actually passes audit_installed_profile('models'), with huggingface_hub0.36.2.
Log C:/Users/Wareen/HawEditCommunity1-existing-gpu-models-audit-20261014.log,
SHA25614b8ac3efe2e1e37de34e20047f5fe68361c13cf41cb3082c44760a2b2480be1.
No installation is needed for this candidate downloader. It does not authorize
the protected integrity-row exception, actual model execution or ASR readiness.
Candidate exact command after approval and manifest reconciliation:
`.venv-gpu/Scripts/python.exe -m hawedit.model_fetch pyannote/speaker-diarization-community-1`.
The earlier approved download attempt did not bypass the blocked manifest or fetch
any weight bytes. The owner subsequently approved this scoped reconciliation,
including the single integrity-row exception and strict historical test transition.
