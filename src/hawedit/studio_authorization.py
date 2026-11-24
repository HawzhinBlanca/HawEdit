"""D-276 signed execution policy consumption; not runtime or cloud certification.

Only a protected host supervisor selects authority paths and computes the execution binding.
Signed references are owner assertions, not independently verified licences, prices or policy.
No HTTP worker is enabled here. Receipts/constructed BillingPolicy values are not capabilities.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hawedit.candidate_review import CandidateReviewError, _canonical, _json, _read, _write
from hawedit.gemini import API_ROOT, Transport
from hawedit.studio_billing import BillingEffects, BillingPolicy, GuardedGeminiTransport
from hawedit.studio_private import PrivateDirectory, StudioStorageError
from hawedit.wsl_setup import package_digest

EXECUTION_NAMESPACE = "hawedit-studio-execution-v1"
_PRINCIPAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@:+-]{0,127}\Z")
_HEX = re.compile(r"[a-f0-9]{64}\Z")
_BILLING_FIELDS = {
    "model_base_url",
    "max_input_tokens",
    "max_output_tokens",
    "thinking_budget",
    "max_billed_thinking_tokens",
    "input_microusd_per_million",
    "output_microusd_per_million",
    "pool_microusd",
}


class StudioAuthorizationError(RuntimeError):
    """Configured execution authority is unavailable, invalid, changed or revoked."""


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    """Host-selected raw context. Never create from browser paths, hashes or flags."""

    packet_dir: Path
    authority_dir: Path
    expected_execution_binding_sha256: str
    ssh_keygen: str = "ssh-keygen"


@dataclass(frozen=True, slots=True)
class ExecutionAuthorization:
    """Descriptive raw-proof receipt. Consumption always reopens the original inputs."""

    document_sha256: str
    signature_sha256: str
    authority_policy_sha256: str
    allowed_signers_sha256: str
    principal: str
    execution_binding_sha256: str
    governance_json: str
    policy: BillingPolicy


@dataclass(frozen=True, slots=True)
class _RawAuthorization:
    packet: PrivateDirectory
    authority: PrivateDirectory
    document: bytes
    signature: bytes
    authority_policy: bytes
    signers: bytes
    max_age: int
    principals: tuple[str, ...]


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: object) -> str:
    if not isinstance(value, str) or _HEX.fullmatch(value) is None:
        raise StudioAuthorizationError("Execution binding requires an exact SHA256 digest")
    return value


def _fields(document: dict[str, Any], fields: set[str]) -> None:
    if set(document) != fields:
        raise StudioAuthorizationError("Execution authorization has an unsupported schema")


def _packet_members(packet: PrivateDirectory) -> None:
    expected = {"authorization.json", "authorization.sig"}
    observed: set[str] = set()
    # Stop early on foreign entries instead of scanning an unbounded directory.
    for item in packet.path.iterdir():
        if item.name not in expected or item.name in observed:
            raise StudioAuthorizationError("Execution proof packet has unexpected members")
        observed.add(item.name)
    packet.verify()
    if observed != expected:
        raise StudioAuthorizationError("Execution proof packet is incomplete")


def _raw(context: AuthorizationContext) -> _RawAuthorization:
    _digest(context.expected_execution_binding_sha256)
    if not isinstance(context.packet_dir, Path) or not isinstance(context.authority_dir, Path):
        raise StudioAuthorizationError("Configured host-private authority paths are required")
    packet = PrivateDirectory(context.packet_dir, create=False)
    authority = PrivateDirectory(context.authority_dir, create=False)
    _packet_members(packet)
    policy_bytes = _read(authority, "policy.json", limit=65536)
    policy = _json(policy_bytes)
    _fields(
        policy,
        {
            "schema",
            "namespace",
            "principals",
            "allowed_signers_sha256",
            "max_authorization_age_seconds",
        },
    )
    if (
        type(policy["schema"]) is not int
        or policy["schema"] != 1
        or policy["namespace"] != EXECUTION_NAMESPACE
        or _canonical(policy) != policy_bytes
    ):
        raise StudioAuthorizationError(
            "Configured execution authority has the wrong purpose/schema"
        )
    principals = policy["principals"]
    if (
        not isinstance(principals, list)
        or not 1 <= len(principals) <= 64
        or any(not isinstance(p, str) or _PRINCIPAL.fullmatch(p) is None for p in principals)
        or len(set(principals)) != len(principals)
    ):
        raise StudioAuthorizationError("Unique configured execution-owner principals are required")
    max_age = policy["max_authorization_age_seconds"]
    if type(max_age) is not int or not 1 <= max_age <= 30 * 86400:
        raise StudioAuthorizationError("Execution authorization freshness must be bounded")
    signers = _read(authority, "allowed_signers", limit=1024 * 1024)
    if not signers or _digest(policy["allowed_signers_sha256"]) != _sha(signers):
        raise StudioAuthorizationError("Configured execution allowed-signers binding changed")
    return _RawAuthorization(
        packet,
        authority,
        _read(packet, "authorization.json", limit=65536),
        _read(packet, "authorization.sig", limit=65536),
        policy_bytes,
        signers,
        max_age,
        tuple(principals),
    )


def _document(
    raw: _RawAuthorization, context: AuthorizationContext
) -> tuple[dict[str, Any], BillingPolicy]:
    document = _json(raw.document)
    _fields(
        document,
        {
            "schema",
            "namespace",
            "principal",
            "issued_at",
            "expires_at",
            "pipeline_source_sha256",
            "execution_binding_sha256",
            "actions",
            "governance",
            "billing",
        },
    )
    if (
        type(document["schema"]) is not int
        or document["schema"] != 1
        or document["namespace"] != EXECUTION_NAMESPACE
        or _canonical(document) != raw.document
        or document["principal"] not in raw.principals
        or document["actions"] != ["countTokens", "generateContent"]
    ):
        raise StudioAuthorizationError(
            "Execution document purpose, owner, actions or canonical bytes are invalid"
        )
    issued, expires = document["issued_at"], document["expires_at"]
    now = time.time()
    if (
        type(issued) is not int
        or type(expires) is not int
        or not 0 < issued <= now < expires <= 253402300799
        or now - issued > raw.max_age
        or expires - issued > raw.max_age
    ):
        raise StudioAuthorizationError("Execution authorization is expired, future or stale")
    if _digest(document["pipeline_source_sha256"]) != package_digest():
        raise StudioAuthorizationError("Signed execution producer package is not current")
    if _digest(document["execution_binding_sha256"]) != context.expected_execution_binding_sha256:
        raise StudioAuthorizationError(
            "Signed execution context differs from the supervisor binding"
        )
    governance = document["governance"]
    billing = document["billing"]
    if not isinstance(governance, dict) or not isinstance(billing, dict):
        raise StudioAuthorizationError(
            "Typed governance references and billing policy are required"
        )
    _fields(
        governance,
        {
            "confidential",
            "retention_reference",
            "rights_reference",
            "model_access_reference",
            "pricing_reference",
        },
    )
    if type(governance["confidential"]) is not bool:
        raise StudioAuthorizationError("Confidentiality must be explicit, not coerced")
    for key in (
        "retention_reference",
        "rights_reference",
        "model_access_reference",
        "pricing_reference",
    ):
        value = governance[key]
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 2048
            or any(ord(char) < 32 for char in value)
        ):
            raise StudioAuthorizationError("Bounded attributed governance references are required")
    _fields(billing, _BILLING_FIELDS)
    policy = BillingPolicy(authorization_sha256=_sha(raw.document), expires_at=expires, **billing)
    if governance["confidential"] and policy.model_base_url.startswith(API_ROOT + "/"):
        raise StudioAuthorizationError("Confidential execution cannot use the Developer API")
    return document, policy


def _unchanged(raw: _RawAuthorization) -> None:
    _packet_members(raw.packet)
    if (
        _read(raw.packet, "authorization.json", limit=65536) != raw.document
        or _read(raw.packet, "authorization.sig", limit=65536) != raw.signature
        or _read(raw.authority, "policy.json", limit=65536) != raw.authority_policy
        or _read(raw.authority, "allowed_signers", limit=1024 * 1024) != raw.signers
    ):
        raise StudioAuthorizationError("Raw execution document/proof/configured trust changed")


def _verify(raw: _RawAuthorization, principal: str, ssh_keygen: str) -> None:
    armor = rb"-----BEGIN SSH SIGNATURE-----\n(?:[A-Za-z0-9+/=]+\n)+-----END SSH SIGNATURE-----\n"
    if not any(re.fullmatch(p, raw.signature) for p in (armor, armor.replace(b"\\n", b"\\r\\n"))):
        raise StudioAuthorizationError("Execution proof must be canonical detached OpenSSH armor")
    executable = shutil.which(ssh_keygen)
    if executable is None:
        raise StudioAuthorizationError("Configured OpenSSH verifier is unavailable")
    parent = PrivateDirectory(raw.packet.path.parent, create=False)
    scratch = parent.child("execution-verify-" + uuid.uuid4().hex, create=True, exclusive=True)
    owned: dict[str, tuple[int, int, int]] = {}
    try:
        for name, data in (("proof.sig", raw.signature), ("allowed_signers", raw.signers)):
            _write(scratch, name, data)
            owned[name] = scratch.member_identity(name)
        result = subprocess.run(
            [
                executable,
                "-Y",
                "verify",
                "-f",
                str(scratch.path / "allowed_signers"),
                "-I",
                principal,
                "-n",
                EXECUTION_NAMESPACE,
                "-s",
                str(scratch.path / "proof.sig"),
            ],
            input=raw.document,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if (
            result.returncode != 0
            or len(result.stdout) + len(result.stderr) > 8192
            or _read(scratch, "proof.sig", limit=65536) != raw.signature
            or _read(scratch, "allowed_signers", limit=1024 * 1024) != raw.signers
        ):
            raise StudioAuthorizationError(
                "Execution signature, owner principal or purpose did not verify"
            )
        _unchanged(raw)
    finally:
        scratch.verify()
        if {p.name for p in scratch.path.iterdir()} != set(owned):
            raise StudioAuthorizationError(
                "Execution verification scratch changed; retained for inspection"
            )
        for name, identity in owned.items():
            if not scratch.remove_owned(name, identity):
                raise StudioAuthorizationError(
                    "Execution proof snapshot changed; retained for inspection"
                )
        scratch.verify()
        scratch.path.rmdir()
        parent.verify()


def load_studio_authorization(context: AuthorizationContext) -> ExecutionAuthorization:
    """Reopen raw owner authority; verify exact current purpose/bindings without network."""
    try:
        raw = _raw(context)
        document, policy = _document(raw, context)
        _verify(raw, document["principal"], context.ssh_keygen)
        # Recheck time and current producer after the bounded subprocess, not just before it.
        repeated, repeated_policy = _document(raw, context)
        _unchanged(raw)
        if repeated != document or repeated_policy != policy:
            raise StudioAuthorizationError("Execution authorization changed during verification")
        return ExecutionAuthorization(
            _sha(raw.document),
            _sha(raw.signature),
            _sha(raw.authority_policy),
            _sha(raw.signers),
            document["principal"],
            document["execution_binding_sha256"],
            _canonical(document["governance"]).decode("utf-8"),
            policy,
        )
    except (
        CandidateReviewError,
        StudioStorageError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise StudioAuthorizationError("Configured raw execution authority was refused") from exc


class SignedStudioTransport:
    """Compose actual billing persistence with raw-proof fences, including cached replay."""

    def __init__(
        self, path: Path, job_id: str, context: AuthorizationContext, upstream: Transport
    ) -> None:
        self._context = context
        self._authorization = load_studio_authorization(context)
        self._upstream = upstream
        self._lock = threading.Lock()
        self._journal = GuardedGeminiTransport(path, job_id, self.policy, self._send)
        self._check()

    @property
    def policy(self) -> BillingPolicy:
        return self._authorization.policy

    @property
    def authorization_sha256(self) -> str:
        """Bind this exact raw document digest into the immutable submission identity."""
        return self._authorization.document_sha256

    def _check(self) -> None:
        if load_studio_authorization(self._context) != self._authorization:
            raise StudioAuthorizationError(
                "Configured execution authority changed; recovery reconciliation required"
            )

    def inspect_effects(self) -> BillingEffects:
        """Fresh descriptive journal read, fenced by actual raw owner proof."""
        with self._lock:
            self._check()
            observed = self._journal.inspect_effects()
            self._check()
            return observed

    def _send(self, url: str, payload: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        self._check()
        response = self._upstream(url, payload, headers)
        self._check()
        return response

    def __call__(
        self, url: str, payload: bytes | None, headers: Mapping[str, str]
    ) -> tuple[int, str]:
        with self._lock:
            self._check()
            result = self._journal(url, payload, headers)
            self._check()
            return result
