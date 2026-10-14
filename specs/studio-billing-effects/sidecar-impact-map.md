# Sidecar Caller Impact

Only PrivateSqlitePath.verify's existing disappearance exception family changes.
Map SHA256831a4b37856bd625cdb445970a62d0f1faa512f4286eebdc46a3bca7ea5a3d6b.
Actual Serena references: PrivateSqlitePath.__init__; studio_admission
inspect_studio_connection/inspect_studio_journal; AttemptStore._connection;
GuardedGeminiTransport._connection; _OwnedEngine._check;
SubmissionStore._connection/work_dir; existing private-storage/admission tests.
Additional captured pairs: _verify_binding, _private, _plain, billing._connection
and the failing concurrent-budget test. No symbol signature or SQLite schema change.

Run complete private-storage, billing, admission, attempts, submissions, runtime,
authorization and claims modules; exact canonical gate includes all remaining
callers. Keep real crash recovery, stable unsafe links/directories, root/main
replacement and storage-outage refusal obligations. Provider requests and refunds
are not retried; no DB lock is held across HTTP.
