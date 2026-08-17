# Specification — editable model-profile audit

- WHEN `audit_installed_profile("models")` runs from the authoritative PEP 660 checkout
  install, THE environment auditor SHALL authenticate the current target lock from that exact
  checkout and validate it against the checkout dependency manifest.
- WHEN the editable lock bytes, dependency contract, project version, or installed locked
  distribution inventory differs, THE environment auditor SHALL refuse with
  `EnvironmentAuditError` before the download client is imported.
- WHEN the authoritative HawEdit distribution is a wheel, THE environment auditor SHALL keep
  requiring the exact RECORD-authenticated packaged lock and installed wheel metadata.
- WHEN editable metadata names a different, missing, malformed, or non-local checkout, THE
  environment auditor SHALL refuse rather than falling back to another checkout or wheel data.
- WHEN the dedicated source-checkout model-fetch environment matches its exact lock, THE
  model-fetch download-client preflight SHALL succeed without requiring a locally built wheel.
