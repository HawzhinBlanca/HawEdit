# EARS Specification

- SH1 WHEN studio is selected on Windows Python3.11, THE installer SHALL validate
  one trusted CUDAcu130 lock for media/gpu/models/diarization/agentic/cloud before
  network/install. Test: test_studio_profile_binds_all_production_extras_and_cuda.
- SH2 WHEN target/backend/extra/contract/byte identity drifts, THE environment SHALL
  refuse before execution. Tests: test_studio_profile_refuses_target_backend_and_contract_drift,
  test_installed_studio_profile_refuses_missing_or_drifted_dependencies.
- SH3 WHEN studio is requested on an unmeasured target, THE environment SHALL
  explicitly refuse. Test: test_studio_profile_refuses_unmeasured_host_targets.
- SH4 WHEN generating host locks, THE maintainer SHALL preserve resolver/date,
  valid exact binary SHA256, HTTPS official origins, per-hop validation and bounds.
  Tests: test_wheel_exporter_accepts_official_torchcodec_origin,
  test_wheel_exporter_refuses_nonhex_sha256,
  test_wheel_exporter_refuses_untrusted_origin_and_redirect,
  test_studio_profile_has_one_exact_hash_per_package.
- SH5 WHEN the wheel is built/installed, THE release validator SHALL require the
  studio lock and installed audits SHALL authenticate RECORD/trusted bytes.
  Tests: test_wheel_requires_studio_profile_lock,
  test_installed_studio_profile_refuses_missing_or_drifted_dependencies.
- SH6 WHEN the native NumPy pin changes, THE target graphs SHALL use the minimum
  compatible patch without unrelated exact-version or canonical WSL ASR drift.
  Test: test_studio_numpy_pin_satisfies_declared_diarization; retain all existing
  target/media/ASR assertions and real five-target structured comparison.

This specification does not authorize model provisioning, cloud spend, signer
enrollment, publication, qualified security or acceptance claims.
