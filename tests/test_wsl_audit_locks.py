from __future__ import annotations

import hashlib
import re

from hawedit.wsl_audit_locks import (
    AUDIT_DISTRIBUTIONS,
    AUDIT_LOCK_SHA256,
    AUDIT_REQUIREMENTS,
)


def test_audit_scanner_lock_is_complete_exact_and_self_authenticating() -> None:
    assert len(AUDIT_DISTRIBUTIONS) == 29
    assert AUDIT_DISTRIBUTIONS["pip-audit"] == "2.10.1"
    assert hashlib.sha256(AUDIT_REQUIREMENTS.encode("utf-8")).hexdigest() == AUDIT_LOCK_SHA256
    assert AUDIT_REQUIREMENTS.count("--hash=sha256:") == len(AUDIT_DISTRIBUTIONS)
    assert " @ " not in AUDIT_REQUIREMENTS
    assert "--index" not in AUDIT_REQUIREMENTS

    entries = re.findall(
        r"(?m)^([a-z0-9-]+)==([^\s]+) \\\n    --hash=sha256:([0-9a-f]{64})$",
        AUDIT_REQUIREMENTS,
    )
    assert len(entries) == len(AUDIT_DISTRIBUTIONS)
    assert {name: version for name, version, _digest in entries} == dict(AUDIT_DISTRIBUTIONS)
    assert len({digest for _name, _version, digest in entries}) == len(entries)
