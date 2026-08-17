# Specification — bounded Path B refusal diagnostics

- **AC-1:** WHEN a Path B survivor is recorded as unreadable, THE system SHALL require a concrete
  non-empty string reason.
- **AC-2:** WHEN that reason contains control characters or arbitrary whitespace, THE system SHALL
  serialize one printable line while preserving an ordinary short one-line reason byte-for-byte.
- **AC-3:** WHEN that reason exceeds the report budget, THE system SHALL cap it deterministically at
  1,024 characters and SHALL NOT retain the discarded tail.
- **AC-4:** WHEN `VideoChat3Reader` catches a per-window `PathBError`, THE reader SHALL retain the
  exception type and bounded useful detail, SHALL record exactly that survivor as unreadable, and
  SHALL continue processing readable survivors.
