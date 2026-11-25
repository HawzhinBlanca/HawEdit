"""Real SSH/private-journal protocol probes, not paid provider or runtime acceptance."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from hawedit.candidate_review import _canonical, _write
from hawedit.gemini import API_ROOT
from hawedit.judge import KURDISH_EDITORIAL_JUDGE
from hawedit.studio_authorization import (
    EXECUTION_NAMESPACE,
    AuthorizationContext,
    SignedStudioTransport,
    StudioAuthorizationError,
    load_studio_authorization,
)
from hawedit.studio_private import PrivateDirectory
from hawedit.workflow_recovery import ExternalReconciliationError
from hawedit.wsl_setup import package_digest


@dataclass(frozen=True)
class SigningTools:
    executable: str
    key: Path
    foreign_key: Path
    public: bytes


@pytest.fixture(scope="module")
def signing_tools(tmp_path_factory: pytest.TempPathFactory) -> SigningTools:
    root = PrivateDirectory(tmp_path_factory.mktemp("execution-signing") / "private")
    executable = shutil.which("ssh-keygen")
    assert executable is not None, "Real OpenSSH is required; absence is not a passing probe"
    for name in ("owner", "foreign"):
        result = subprocess.run(
            [executable, "-q", "-t", "ed25519", "-N", "", "-f", str(root.path / name)],
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode(errors="replace")
    return SigningTools(
        executable,
        root.path / "owner",
        root.path / "foreign",
        (root.path / "owner.pub").read_bytes(),
    )


def _replace(directory: PrivateDirectory, name: str, data: bytes) -> None:
    if (directory.path / name).exists():
        assert directory.remove_owned(name, directory.member_identity(name))
    _write(directory, name, data)


@dataclass
class AuthorizationCase:
    root: PrivateDirectory
    authority: PrivateDirectory
    packet: PrivateDirectory
    document: dict[str, Any]
    authority_policy: dict[str, Any]
    signers: bytes
    tools: SigningTools

    @property
    def context(self) -> AuthorizationContext:
        # Synthetic execution identity: this test never claims runtime/model readiness.
        return AuthorizationContext(
            self.packet.path, self.authority.path, "d" * 64, self.tools.executable
        )

    def sign(self, *, key: Path | None = None, namespace: str = EXECUTION_NAMESPACE) -> None:
        raw = _canonical(self.document)
        _replace(self.packet, "authorization.json", raw)
        self.sign_raw(raw, key=key, namespace=namespace)

    def sign_raw(
        self, raw: bytes, *, key: Path | None = None, namespace: str = EXECUTION_NAMESPACE
    ) -> None:
        result = subprocess.run(
            [
                self.tools.executable,
                "-Y",
                "sign",
                "-f",
                str(key or self.tools.key),
                "-n",
                namespace,
            ],
            input=raw,
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        _replace(self.packet, "authorization.sig", result.stdout)

    def revoke(self) -> None:
        changed = b"# owner revoked for this protocol probe\n"
        policy = {
            **self.authority_policy,
            "allowed_signers_sha256": hashlib.sha256(changed).hexdigest(),
        }
        _replace(self.authority, "allowed_signers", changed)
        _replace(self.authority, "policy.json", _canonical(policy))

    def restore(self) -> None:
        _replace(self.authority, "allowed_signers", self.signers)
        _replace(self.authority, "policy.json", _canonical(self.authority_policy))


@pytest.fixture
def authorization_case(tmp_path: Path, signing_tools: SigningTools) -> AuthorizationCase:
    root = PrivateDirectory(tmp_path / "private")
    authority = root.child("owner-authority", create=True)
    packet = root.child("execution-packet", create=True)
    signers = b"studio-owner " + signing_tools.public
    authority_policy = {
        "schema": 1,
        "namespace": EXECUTION_NAMESPACE,
        "principals": ["studio-owner"],
        "allowed_signers_sha256": hashlib.sha256(signers).hexdigest(),
        "max_authorization_age_seconds": 3600,
    }
    _write(authority, "allowed_signers", signers)
    _write(authority, "policy.json", _canonical(authority_policy))
    now = int(time.time())
    document = {
        "schema": 1,
        "namespace": EXECUTION_NAMESPACE,
        "principal": "studio-owner",
        "issued_at": now,
        "expires_at": now + 300,
        "pipeline_source_sha256": package_digest(),
        "execution_binding_sha256": "d" * 64,
        "actions": ["countTokens", "generateContent"],
        "governance": {
            "confidential": False,
            "retention_reference": "local-protocol-probe-only",
            "rights_reference": "local-protocol-probe-only",
            "model_access_reference": "local-protocol-probe-only",
            "pricing_reference": "local-protocol-probe-only",
        },
        "billing": {
            "model_base_url": API_ROOT + "/models/" + KURDISH_EDITORIAL_JUDGE,
            "max_input_tokens": 100,
            "max_output_tokens": 5,
            "thinking_budget": 128,
            "max_billed_thinking_tokens": 128,
            "input_microusd_per_million": 1_000_000,
            "output_microusd_per_million": 1_000_000,
            "pool_microusd": 1000,
        },
    }
    case = AuthorizationCase(
        root, authority, packet, document, authority_policy, signers, signing_tools
    )
    case.sign()
    return case


class ProtocolProbe:
    """Deterministic provider boundary; no network, model, price or account claim."""

    def __init__(self, case: AuthorizationCase, *, revoke_on: str | None = None) -> None:
        self.case = case
        self.revoke_on = revoke_on
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def __call__(
        self, url: str, payload: bytes | None, headers: Mapping[str, str]
    ) -> tuple[int, str]:
        assert payload is not None
        assert headers == {"X-Probe": "local-only"}
        self.requests.append((url, json.loads(payload)))
        operation = url.rsplit(":", 1)[-1]
        if operation == self.revoke_on:
            self.case.revoke()
        if operation == "countTokens":
            return 200, '{"totalTokens":7}'
        assert operation == "generateContent"
        return 200, json.dumps(
            {
                "candidates": [{"content": {"parts": [{"text": "protocol-result"}]}}],
                "usageMetadata": {
                    "promptTokenCount": 7,
                    "candidatesTokenCount": 2,
                    "thoughtsTokenCount": 3,
                    "totalTokenCount": 12,
                },
            }
        )


def _transport(
    case: AuthorizationCase, probe: ProtocolProbe, job: str = "a"
) -> SignedStudioTransport:
    return SignedStudioTransport(
        case.root.path / "billing.sqlite", "studio-" + job * 64, case.context, probe
    )


def _generate(transport: SignedStudioTransport) -> tuple[int, str]:
    return transport(
        transport.policy.model_base_url + ":generateContent",
        b'{"contents":[{"parts":[{"text":"protocol probe"}]}],"generationConfig":{}}',
        {"X-Probe": "local-only"},
    )


def test_signed_studio_effects_is_descriptive_only(authorization_case: AuthorizationCase) -> None:
    probe = ProtocolProbe(authorization_case)
    client = _transport(authorization_case, probe)
    observed = client.inspect_effects()
    assert observed.authorization_sha256 == client.authorization_sha256
    assert observed.effects == observed.outstanding_intents == ()
    assert probe.requests == []
    assert not hasattr(observed, "completed")
    assert not hasattr(observed, "is_quiescent")


def test_signed_studio_effects_reopens_raw_authority(authorization_case: AuthorizationCase) -> None:
    probe = ProtocolProbe(authorization_case)
    client = _transport(authorization_case, probe)
    authorization_case.revoke()
    with pytest.raises(StudioAuthorizationError):
        client.inspect_effects()
    assert probe.requests == []


def test_signed_studio_effects_rechecks_after_actual_sqlite_read(
    authorization_case: AuthorizationCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = ProtocolProbe(authorization_case)
    client = _transport(authorization_case, probe)
    actual_connection = client._journal._connection
    revoked = False

    def native_authorizer(
        action: int,
        table: str | None,
        column: str | None,
        database: str | None,
        trigger: str | None,
    ) -> int:
        nonlocal revoked
        if action == sqlite3.SQLITE_READ and table == "calls" and not revoked:
            revoked = True
            authorization_case.revoke()
        return sqlite3.SQLITE_OK

    @contextmanager
    def connection() -> Any:
        with actual_connection() as db:
            db.set_authorizer(native_authorizer)
            yield db

    monkeypatch.setattr(client._journal, "_connection", connection)
    with pytest.raises(StudioAuthorizationError):
        client.inspect_effects()
    assert revoked
    assert probe.requests == []


def test_signed_studio_authorization_binds_real_proof_and_policy(
    authorization_case: AuthorizationCase,
) -> None:
    case = authorization_case
    evidence = load_studio_authorization(case.context)
    assert evidence.document_sha256 == hashlib.sha256(_canonical(case.document)).hexdigest()
    assert evidence.policy.authorization_sha256 == evidence.document_sha256
    assert evidence.policy.expires_at == case.document["expires_at"]
    assert evidence.policy.reservation(7) == 140
    assert evidence.principal == "studio-owner"
    assert evidence.execution_binding_sha256 == "d" * 64
    assert evidence.allowed_signers_sha256 == hashlib.sha256(case.signers).hexdigest()
    assert not hasattr(evidence, "verified")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", True),
        ("schema", 2),
        ("namespace", "hawedit-candidate-review-v1"),
        ("principal", "foreign"),
        ("issued_at", 253402300799),
        ("issued_at", 1),
        ("expires_at", 1),
        ("expires_at", 253402300799),
        ("pipeline_source_sha256", "a" * 64),
        ("execution_binding_sha256", "b" * 64),
        ("actions", ["countTokens", "generateContent", "publish"]),
        ("unknown", True),
    ],
)
def test_signed_studio_authorization_refuses_invalid_signed_document(
    authorization_case: AuthorizationCase, field: str, value: object
) -> None:
    case = authorization_case
    assert load_studio_authorization(case.context).principal == "studio-owner"
    case.document[field] = value
    case.sign()
    with pytest.raises(StudioAuthorizationError):
        load_studio_authorization(case.context)


@pytest.mark.parametrize("field", ["max_input_tokens", "max_output_tokens", "pool_microusd"])
def test_signed_studio_authorization_refuses_boolean_budget(
    authorization_case: AuthorizationCase, field: str
) -> None:
    case = authorization_case
    assert load_studio_authorization(case.context).principal == "studio-owner"
    case.document["billing"][field] = True
    case.sign()
    with pytest.raises(StudioAuthorizationError):
        load_studio_authorization(case.context)


@pytest.mark.parametrize(
    "damage", ["foreign-key", "other-purpose", "duplicate-key", "noncanonical"]
)
def test_signed_studio_authorization_refuses_wrong_key_or_namespace(
    authorization_case: AuthorizationCase, damage: str
) -> None:
    case = authorization_case
    assert load_studio_authorization(case.context).principal == "studio-owner"
    if damage == "foreign-key":
        case.sign(key=case.tools.foreign_key)
    elif damage == "other-purpose":
        case.sign(namespace="hawedit-candidate-review-v1")
    else:
        raw = _canonical(case.document)
        raw = b'{"schema":1,' + raw[1:] if damage == "duplicate-key" else raw + b" "
        _replace(case.packet, "authorization.json", raw)
        case.sign_raw(raw)
    with pytest.raises(StudioAuthorizationError):
        load_studio_authorization(case.context)


def test_signed_studio_authorization_refuses_confidential_developer_route(
    authorization_case: AuthorizationCase,
) -> None:
    case = authorization_case
    case.document["governance"]["confidential"] = True
    case.sign()
    with pytest.raises(StudioAuthorizationError):
        load_studio_authorization(case.context)


def test_signed_studio_transport_replays_under_current_raw_authority(
    authorization_case: AuthorizationCase,
) -> None:
    case = authorization_case
    probe = ProtocolProbe(case)
    first = _generate(_transport(case, probe))
    assert first[0] == 200 and "protocol-result" in first[1]
    assert len(probe.requests) == 2
    config = probe.requests[1][1]["generationConfig"]
    assert config["maxOutputTokens"] == 5 and config["candidateCount"] == 1
    assert config["thinkingConfig"] == {"thinkingBudget": 128}
    assert _generate(_transport(case, probe)) == first
    assert len(probe.requests) == 2


def test_signed_studio_transport_reopens_authority_for_replay(
    authorization_case: AuthorizationCase,
) -> None:
    case = authorization_case
    probe = ProtocolProbe(case)
    assert _generate(_transport(case, probe))[0] == 200
    replay = _transport(case, probe)
    case.revoke()
    with pytest.raises(StudioAuthorizationError):
        _generate(replay)
    assert len(probe.requests) == 2


def test_signed_studio_transport_refuses_changed_raw_proof(
    authorization_case: AuthorizationCase,
) -> None:
    case = authorization_case
    probe = ProtocolProbe(case)
    transport = _transport(case, probe)
    signature = (case.packet.path / "authorization.sig").read_bytes()
    _replace(case.packet, "authorization.sig", signature + b"\n")
    with pytest.raises(StudioAuthorizationError):
        _generate(transport)
    assert probe.requests == []


def test_signed_studio_transport_rechecks_after_count(
    authorization_case: AuthorizationCase,
) -> None:
    case = authorization_case
    probe = ProtocolProbe(case, revoke_on="countTokens")
    with pytest.raises(ExternalReconciliationError, match="count unavailable"):
        _generate(_transport(case, probe))
    assert len(probe.requests) == 1 and probe.requests[0][0].endswith(":countTokens")
    with sqlite3.connect(case.root.path / "billing.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0


def test_signed_studio_transport_retains_uncertainty_after_revocation(
    authorization_case: AuthorizationCase,
) -> None:
    case = authorization_case
    probe = ProtocolProbe(case, revoke_on="generateContent")
    with pytest.raises(ExternalReconciliationError, match="uncertain"):
        _generate(_transport(case, probe))
    assert len(probe.requests) == 2
    with sqlite3.connect(case.root.path / "billing.sqlite") as db:
        assert db.execute(
            "SELECT state,reservation_microusd,response_json FROM calls"
        ).fetchall() == [("intent", 140, None)]
    case.restore()
    with pytest.raises(ExternalReconciliationError, match="uncertain"):
        _generate(_transport(case, probe))
    assert len(probe.requests) == 2


def test_signed_studio_transport_shares_signed_reservation_pool(
    authorization_case: AuthorizationCase,
) -> None:
    case = authorization_case
    case.document["billing"]["pool_microusd"] = 200
    case.sign()
    probe = ProtocolProbe(case)
    assert _generate(_transport(case, probe))[0] == 200
    with pytest.raises(ExternalReconciliationError, match="budget exhausted"):
        _generate(_transport(case, probe, job="b"))
    assert sum(url.endswith(":generateContent") for url, _body in probe.requests) == 1
    with sqlite3.connect(case.root.path / "billing.sqlite") as db:
        assert db.execute("SELECT SUM(reservation_microusd) FROM calls").fetchone()[0] == 140


def test_signed_studio_authorization_refuses_unsafe_storage(
    authorization_case: AuthorizationCase,
) -> None:
    case = authorization_case
    target = case.authority.path / "allowed_signers"
    before = target.read_bytes(), target.stat().st_mode
    alias = case.root.path / "signers-alias"
    os.link(target, alias)
    with pytest.raises(StudioAuthorizationError):
        load_studio_authorization(case.context)
    assert (target.read_bytes(), target.stat().st_mode) == before
    assert alias.read_bytes() == before[0] and alias.exists()


def test_signed_studio_authorization_refuses_missing_owner_tool(
    authorization_case: AuthorizationCase,
) -> None:
    with pytest.raises(StudioAuthorizationError):
        load_studio_authorization(
            replace(authorization_case.context, ssh_keygen="missing-hawedit-tool")
        )


def test_signed_studio_transport_guards_direct_token_count(
    authorization_case: AuthorizationCase,
) -> None:
    case = authorization_case
    probe = ProtocolProbe(case)
    transport = _transport(case, probe)
    arguments = (
        transport.policy.model_base_url + ":countTokens",
        b'{"contents":[{"parts":[{"text":"protocol probe"}]}]}',
        {"X-Probe": "local-only"},
    )
    assert transport(*arguments) == (200, '{"totalTokens":7}')
    assert len(probe.requests) == 1
    case.revoke()
    with pytest.raises(StudioAuthorizationError):
        transport(*arguments)
    assert len(probe.requests) == 1
    with sqlite3.connect(case.root.path / "billing.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0


@pytest.mark.parametrize("damage", ["missing-document", "missing-signature", "foreign-member"])
def test_signed_studio_authorization_requires_exact_raw_packet(
    authorization_case: AuthorizationCase, damage: str
) -> None:
    case = authorization_case
    assert load_studio_authorization(case.context).principal == "studio-owner"
    if damage == "foreign-member":
        _write(case.packet, "unexpected.json", b"{}")
    else:
        name = "authorization.json" if damage == "missing-document" else "authorization.sig"
        assert case.packet.remove_owned(name, case.packet.member_identity(name))
    probe = ProtocolProbe(case)
    with pytest.raises(StudioAuthorizationError):
        _transport(case, probe)
    assert probe.requests == []
    assert not (case.root.path / "billing.sqlite").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("namespace", "hawedit-candidate-review-v1"),
        ("principals", ["studio-owner", "studio-owner"]),
        ("principals", [True]),
        ("max_authorization_age_seconds", True),
        ("allowed_signers_sha256", "f" * 64),
    ],
)
def test_signed_studio_authorization_refuses_changed_owner_policy(
    authorization_case: AuthorizationCase, field: str, value: object
) -> None:
    case = authorization_case
    assert load_studio_authorization(case.context).principal == "studio-owner"
    changed = {**case.authority_policy, field: value}
    _replace(case.authority, "policy.json", _canonical(changed))
    with pytest.raises(StudioAuthorizationError):
        load_studio_authorization(case.context)


def test_signed_studio_transport_never_adopts_resigned_policy_in_existing_job(
    authorization_case: AuthorizationCase,
) -> None:
    case = authorization_case
    probe = ProtocolProbe(case)
    transport = _transport(case, probe)
    original = transport.authorization_sha256
    case.document["billing"]["pool_microusd"] = 2000
    case.sign()
    assert load_studio_authorization(case.context).document_sha256 != original
    with pytest.raises(StudioAuthorizationError, match="changed"):
        _generate(transport)
    assert probe.requests == []
    with sqlite3.connect(case.root.path / "billing.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM policies").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0
