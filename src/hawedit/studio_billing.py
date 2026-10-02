"""Private billed-call intent and response evidence for a trusted studio supervisor.

Policy values are not authenticated spending/governance approval. Production adoption must
verify that authority and provider cap/pricing semantics. Reservations are not invoices.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from hawedit.gemini import API_ROOT, Transport
from hawedit.judge import KURDISH_EDITORIAL_JUDGE, PRO_TIER_TOKEN_CEILING
from hawedit.studio_private import PrivateSqlitePath
from hawedit.studio_submissions import StudioStorageError
from hawedit.workflow_recovery import ExternalReconciliationError

__all__ = ["BillingPolicy", "GuardedGeminiTransport"]

_MAX_REQUEST_BYTES = 16 << 20
_MAX_RESPONSE_BYTES = 1 << 20
_HEX = re.compile(r"[a-f0-9]{64}\Z")
_VERTEX = re.compile(
    r"https://(?:[a-z][a-z0-9-]*-)?aiplatform\.googleapis\.com/v1/projects/"
    r"[A-Za-z0-9][A-Za-z0-9._:-]*/locations/[a-z][a-z0-9-]*/publishers/google/models/"
    + re.escape(KURDISH_EDITORIAL_JUDGE)
    + r"\Z"
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _call_id(
    job: str, request: str, occurrence: int, tokens: int, reservation: int, policy: str
) -> str:
    return _digest(_canonical([job, request, occurrence, tokens, reservation, policy]))


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _object(value: bytes | str, ceiling: int) -> dict[str, Any]:
    size = len(value) if isinstance(value, bytes) else len(value.encode("utf-8"))
    if size > ceiling:
        raise ValueError("JSON exceeds the bounded protocol size")
    result: object = json.loads(value, object_pairs_hook=_pairs)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")
    _canonical(result)
    return result


def _integer(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


@dataclass(frozen=True, slots=True)
class BillingPolicy:
    authorization_sha256: str
    model_base_url: str
    expires_at: int
    max_input_tokens: int
    max_output_tokens: int
    thinking_budget: int
    max_billed_thinking_tokens: int
    input_microusd_per_million: int
    output_microusd_per_million: int
    pool_microusd: int

    def __post_init__(self) -> None:
        if not isinstance(self.authorization_sha256, str) or not _HEX.fullmatch(
            self.authorization_sha256
        ):
            raise ValueError("A bound authorization digest is required, not an approval flag")
        if (
            not isinstance(self.model_base_url, str)
            or len(self.model_base_url) > 512
            or (
                self.model_base_url != API_ROOT + "/models/" + KURDISH_EDITORIAL_JUDGE
                and not _VERTEX.fullmatch(self.model_base_url)
            )
        ):
            raise ValueError("Unsupported canonical model route")
        limits = {
            "expires_at": (1, 253402300799),
            "max_input_tokens": (1, PRO_TIER_TOKEN_CEILING),
            "max_output_tokens": (1, 65536),
            "thinking_budget": (128, 32768),
            "max_billed_thinking_tokens": (self.thinking_budget, 65536),
            "input_microusd_per_million": (1, 10**12),
            "output_microusd_per_million": (1, 10**12),
            "pool_microusd": (1, 10**15),
        }
        for field, (low, high) in limits.items():
            if not _integer(getattr(self, field), low, high):
                raise ValueError(f"Invalid bounded billing policy field: {field}")

    def reservation(self, input_tokens: int) -> int:
        numerator = (
            input_tokens * self.input_microusd_per_million
            + (self.max_output_tokens + self.max_billed_thinking_tokens)
            * self.output_microusd_per_million
        )
        return (numerator + 999999) // 1_000_000


def _contents(document: dict[str, Any]) -> None:
    contents = document.get("contents")
    if not isinstance(contents, list) or not contents:
        raise ValueError("Nonempty bounded contents required")
    for content in contents:
        if not isinstance(content, dict) or set(content) - {"parts", "role"}:
            raise ValueError("Unsupported content fields")
        if "role" in content and content["role"] not in ("user", "model"):
            raise ValueError("Unsupported content role")
        parts = content.get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError("Nonempty content parts required")
        for part in parts:
            if not isinstance(part, dict):
                raise ValueError("Unsupported content part")
            if set(part) == {"text"} and isinstance(part["text"], str):
                continue
            inline = part.get("inlineData")
            if (
                set(part) == {"inlineData"}
                and isinstance(inline, dict)
                and set(inline) == {"mimeType", "data"}
                and all(isinstance(v, str) for v in inline.values())
            ):
                continue
            raise ValueError(
                "Only literal text and inline media are supported; no remote files/tools"
            )


class GuardedGeminiTransport:
    def __init__(self, path: Path, job_id: str, policy: BillingPolicy, upstream: Transport) -> None:
        if not re.fullmatch(r"studio-[a-f0-9]{64}", job_id):
            raise ValueError("A content-bound studio job ID is required")
        self._storage = PrivateSqlitePath(path)
        self.job_id = job_id
        self.policy = policy
        self.upstream = upstream
        self._policy_json = _canonical(asdict(policy))
        self._occurrences: dict[str, int] = {}
        self._lock = threading.Lock()
        with self._connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if version not in (0, 1) or (version == 0 and tables):
                raise StudioStorageError("Unsupported billing database schema")
            if version == 1:
                columns = {
                    "policies": ("id", "policy_json"),
                    "calls": (
                        "id",
                        "policy_id",
                        "job_id",
                        "request_sha256",
                        "occurrence",
                        "input_tokens",
                        "reservation_microusd",
                        "state",
                        "response_json",
                        "response_sha256",
                    ),
                }
                if {row[0] for row in tables} != set(columns):
                    raise StudioStorageError("Unrecognized billing database tables")
                for name, expected in columns.items():
                    # Names are fixed above, never supplied by a request or stored JSON.
                    if (
                        tuple(row[1] for row in db.execute(f"PRAGMA table_info({name})"))
                        != expected
                    ):
                        raise StudioStorageError("Unrecognized billing database columns")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS policies "
                "(id TEXT PRIMARY KEY, policy_json TEXT NOT NULL)"
            )
            db.execute("""CREATE TABLE IF NOT EXISTS calls (
                id TEXT PRIMARY KEY, policy_id TEXT NOT NULL REFERENCES policies(id),
                job_id TEXT NOT NULL, request_sha256 TEXT NOT NULL, occurrence INTEGER NOT NULL,
                input_tokens INTEGER NOT NULL CHECK(input_tokens>=0),
                reservation_microusd INTEGER NOT NULL CHECK(reservation_microusd>0),
                state TEXT NOT NULL CHECK(state IN ('intent','confirmed')),
                response_json TEXT, response_sha256 TEXT,
                UNIQUE(job_id, request_sha256, occurrence))""")
            db.execute("PRAGMA user_version=1")
            row = db.execute(
                "SELECT substr(policy_json,1,4097) FROM policies WHERE id=?",
                (policy.authorization_sha256,),
            ).fetchone()
            if row is not None and row[0] != self._policy_json:
                raise StudioStorageError(
                    "Existing authorization pool policy conflicts with supplied policy"
                )
            db.execute(
                "INSERT OR IGNORE INTO policies VALUES (?,?)",
                (policy.authorization_sha256, self._policy_json),
            )

    @property
    def path(self) -> Path:
        return self._storage.path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db: sqlite3.Connection | None = None
        try:
            self._storage.verify()
            db = sqlite3.connect(self.path, timeout=5.0)
            self._storage.verify()
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            yield db
            self._storage.verify()
            db.commit()
            self._storage.verify()
        except sqlite3.Error as exc:
            raise StudioStorageError("Billing persistence unavailable or corrupt") from exc
        finally:
            if db is not None:
                db.close()
                self._storage.verify()

    def _existing(self, db: sqlite3.Connection, request_hash: str, occurrence: int) -> str | None:
        self._pool_used(db)
        if db.execute(
            "SELECT 1 FROM calls WHERE job_id=? AND policy_id<>? LIMIT 1",
            (self.job_id, self.policy.authorization_sha256),
        ).fetchone():
            raise StudioStorageError("Job billing policy identity changed")
        # An unresolved charge blocks even a changed request for the same job.
        if db.execute(
            "SELECT 1 FROM calls WHERE job_id=? AND state='intent' LIMIT 1", (self.job_id,)
        ).fetchone():
            raise ExternalReconciliationError(
                "Billed outcome uncertain; attributed provider reconciliation required"
            )
        row = db.execute(
            """SELECT policy_id, input_tokens, reservation_microusd, state,
            substr(response_json,1,1048577), length(CAST(response_json AS BLOB)), response_sha256
            FROM calls WHERE job_id=? AND request_sha256=? AND occurrence=?""",
            (self.job_id, request_hash, occurrence),
        ).fetchone()
        if row is None:
            return None
        policy_id, tokens, reservation, state, body, size, digest = row
        if (
            policy_id != self.policy.authorization_sha256
            or state != "confirmed"
            or not _integer(tokens, 0, self.policy.max_input_tokens)
            or reservation != self.policy.reservation(tokens)
        ):
            raise StudioStorageError("Billed call identity/policy evidence changed")
        if (
            not isinstance(body, str)
            or not _integer(size, 1, _MAX_RESPONSE_BYTES)
            or _digest(body) != digest
        ):
            raise StudioStorageError("Billed response evidence changed or missing")
        try:
            self._validate_response(body, tokens)
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise StudioStorageError("Stored billed response evidence is invalid") from exc
        return body

    def _pool_used(self, db: sqlite3.Connection) -> int:
        row = db.execute(
            "SELECT substr(policy_json,1,4097) FROM policies WHERE id=?",
            (self.policy.authorization_sha256,),
        ).fetchone()
        if row is None or row[0] != self._policy_json:
            raise StudioStorageError("Reservation pool policy evidence changed")
        used = 0
        rows = db.execute(
            """SELECT substr(id,1,65), substr(job_id,1,72), substr(request_sha256,1,65),
            occurrence,input_tokens,reservation_microusd FROM calls WHERE policy_id=?""",
            (self.policy.authorization_sha256,),
        )
        for identity, job, request, occurrence, tokens, reservation in rows:
            if (
                not isinstance(job, str)
                or not re.fullmatch(r"studio-[a-f0-9]{64}", job)
                or not isinstance(request, str)
                or not _HEX.fullmatch(request)
                or not _integer(occurrence, 0, 1_000_000)
                or not _integer(tokens, 0, self.policy.max_input_tokens)
                or reservation != self.policy.reservation(tokens)
                or identity
                != _call_id(
                    job, request, occurrence, tokens, reservation, self.policy.authorization_sha256
                )
            ):
                raise StudioStorageError("Billed reservation identity or arithmetic changed")
            used += reservation
            if used > self.policy.pool_microusd:
                raise StudioStorageError("Billed reservation pool evidence exceeds budget")
        return used

    def _validate_response(self, body: str, tokens: int) -> None:
        document = _object(body, _MAX_RESPONSE_BYTES)
        usage = document.get("usageMetadata")
        if not isinstance(usage, dict):
            raise ValueError("Missing provider usage")
        prompt = usage.get("promptTokenCount")
        output = usage.get("candidatesTokenCount")
        thoughts = usage.get("thoughtsTokenCount", 0)
        total = usage.get("totalTokenCount")
        if (
            not _integer(prompt, 0, tokens)
            or not _integer(output, 0, self.policy.max_output_tokens)
            or not _integer(thoughts, 0, self.policy.max_billed_thinking_tokens)
        ):
            raise ValueError("Provider usage exceeds its reserved bound or has invalid types")
        assert isinstance(prompt, int) and isinstance(output, int) and isinstance(thoughts, int)
        if (
            type(total) is not int
            or total != prompt + output + thoughts
            or usage.get("toolUsePromptTokenCount", 0) != 0
        ):
            raise ValueError("Provider usage does not reconcile")

    def __call__(
        self, url: str, payload: bytes | None, headers: Mapping[str, str]
    ) -> tuple[int, str]:
        with self._lock:
            return self._call(url, payload, headers)

    def _send(self, url: str, payload: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        self._storage.verify()
        result = self.upstream(url, payload, headers)
        self._storage.verify()
        return result

    def _call(self, url: str, payload: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        base = self.policy.model_base_url
        if url not in (base + ":countTokens", base + ":generateContent"):
            raise ExternalReconciliationError("Unapproved model route; no request sent")
        if time.time() >= self.policy.expires_at:
            raise ExternalReconciliationError("Spending policy expired; no request sent")
        try:
            if not isinstance(payload, bytes):
                raise ValueError("A bounded request body is required")
            document = _object(payload, _MAX_REQUEST_BYTES)
            _contents(document)
            if url.endswith(":countTokens"):
                if set(document) != {"contents"}:
                    raise ValueError("Unsupported count request")
                return self._send(url, payload, headers)
            if set(document) != {"contents", "generationConfig"}:
                raise ValueError("Unsupported or unpriced generation fields")
            config = document["generationConfig"]
            if not isinstance(config, dict) or set(config) - {
                "responseMimeType",
                "responseSchema",
                "temperature",
                "maxOutputTokens",
                "thinkingConfig",
                "candidateCount",
            }:
                raise ValueError("Unsupported or unpriced generation configuration")
            caps = {
                "maxOutputTokens": self.policy.max_output_tokens,
                "thinkingConfig": {"thinkingBudget": self.policy.thinking_budget},
                "candidateCount": 1,
            }
            for key, value in caps.items():
                if key in config and _canonical(config[key]) != _canonical(value):
                    raise ValueError("Generation caps conflict with authorized policy")
                config[key] = value
            effective = _canonical(document)
            if len(effective.encode("utf-8")) > _MAX_REQUEST_BYTES:
                raise ValueError("Effective request exceeds protocol bound")
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise ExternalReconciliationError(
                "Invalid bounded/capped request; no generation sent"
            ) from exc

        request_hash = _digest(effective)
        occurrence = self._occurrences.get(request_hash, 0)
        if occurrence > 1_000_000:
            raise ExternalReconciliationError("Billed call occurrence limit exceeded")
        with self._connection() as db:
            confirmed = self._existing(db, request_hash, occurrence)
        if confirmed is not None:
            self._occurrences[request_hash] = occurrence + 1
            return 200, confirmed

        count_document = (
            {**document, "model": base.split("/v1/")[-1]}
            if _VERTEX.fullmatch(base)
            else {
                "generateContentRequest": {**document, "model": "models/" + KURDISH_EDITORIAL_JUDGE}
            }
        )
        try:
            status, count_body = self._send(
                base + ":countTokens", _canonical(count_document).encode("utf-8"), headers
            )
        except Exception as exc:
            raise ExternalReconciliationError(
                "Provider count unavailable; no generation sent"
            ) from exc
        try:
            counted = _object(count_body, _MAX_RESPONSE_BYTES).get("totalTokens")
            if status != 200 or not _integer(counted, 0, self.policy.max_input_tokens):
                raise ValueError("Invalid or over-limit provider count")
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise ExternalReconciliationError(
                "Provider count invalid or exceeds authorized bound; no generation sent"
            ) from exc
        assert isinstance(counted, int)
        reservation = self.policy.reservation(counted)
        call_id = _call_id(
            self.job_id,
            request_hash,
            occurrence,
            counted,
            reservation,
            self.policy.authorization_sha256,
        )
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            confirmed = self._existing(db, request_hash, occurrence)
            if confirmed is not None:
                self._occurrences[request_hash] = occurrence + 1
                return 200, confirmed
            used = self._pool_used(db)
            if (
                not _integer(used, 0, self.policy.pool_microusd)
                or used + reservation > self.policy.pool_microusd
            ):
                raise ExternalReconciliationError(
                    "Authorized reservation budget exhausted; no generation sent"
                )
            if time.time() >= self.policy.expires_at:
                raise ExternalReconciliationError(
                    "Spending policy expired during count; no generation sent"
                )
            db.execute(
                "INSERT INTO calls VALUES (?,?,?,?,?,?,?,'intent',NULL,NULL)",
                (
                    call_id,
                    self.policy.authorization_sha256,
                    self.job_id,
                    request_hash,
                    occurrence,
                    counted,
                    reservation,
                ),
            )

        # Once intent commits, every missing/invalid response remains uncertain, including a
        # persistence failure after an apparently successful HTTP response. Never blind-retry.
        try:
            if time.time() >= self.policy.expires_at:
                raise ValueError("Policy expired after intent commit")
            status, body = self._send(url, effective.encode("utf-8"), headers)
            if status != 200:
                raise ValueError("Unconfirmed provider outcome")
            self._validate_response(body, counted)
            with self._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                result = db.execute(
                    "UPDATE calls SET state='confirmed',response_json=?,response_sha256=? "
                    "WHERE id=? AND state='intent'",
                    (body, _digest(body), call_id),
                )
                if result.rowcount != 1:
                    raise StudioStorageError("Billed intent disappeared or changed")
        except Exception as exc:
            raise ExternalReconciliationError(
                "Billed outcome uncertain; response not durably confirmed; "
                "provider reconciliation required"
            ) from exc
        self._occurrences[request_hash] = occurrence + 1
        return 200, body
