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

__all__ = ["BilledEffect", "BillingEffects", "BillingPolicy", "GuardedGeminiTransport"]

_MAX_REQUEST_BYTES = 16 << 20
_MAX_RESPONSE_BYTES = 1 << 20
_POLICIES_SQL = "CREATE TABLE policies (id TEXT PRIMARY KEY, policy_json TEXT NOT NULL)"
_CALLS_SQL = """CREATE TABLE calls (
                id TEXT PRIMARY KEY, policy_id TEXT NOT NULL REFERENCES policies(id),
                job_id TEXT NOT NULL, request_sha256 TEXT NOT NULL, occurrence INTEGER NOT NULL,
                input_tokens INTEGER NOT NULL CHECK(input_tokens>=0),
                reservation_microusd INTEGER NOT NULL CHECK(reservation_microusd>0),
                state TEXT NOT NULL CHECK(state IN ('intent','confirmed')),
                response_json TEXT, response_sha256 TEXT,
                UNIQUE(job_id, request_sha256, occurrence))"""
_SCHEMA = {
    ("table", "policies", "policies", _POLICIES_SQL),
    ("table", "calls", "calls", _CALLS_SQL),
    ("index", "sqlite_autoindex_policies_1", "policies", None),
    ("index", "sqlite_autoindex_calls_1", "calls", None),
    ("index", "sqlite_autoindex_calls_2", "calls", None),
}
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


def _validate_usage(body: str, tokens: int, policy: BillingPolicy) -> None:
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
        or not _integer(output, 0, policy.max_output_tokens)
        or not _integer(thoughts, 0, policy.max_billed_thinking_tokens)
    ):
        raise ValueError("Provider usage exceeds its reserved bound or has invalid types")
    assert isinstance(prompt, int) and isinstance(output, int) and isinstance(thoughts, int)
    if (
        type(total) is not int
        or total != prompt + output + thoughts
        or usage.get("toolUsePromptTokenCount", 0) != 0
    ):
        raise ValueError("Provider usage does not reconcile")


@dataclass(slots=True)
class _JournalBudget:
    max_rows: int
    max_bytes: int
    deadline: float
    rows: int = 0
    size: int = 0

    def check(self, *, size: int = 0, row: bool = False) -> None:
        self.size += size
        self.rows += int(row)
        if (
            self.rows > self.max_rows
            or self.size > self.max_bytes
            or time.perf_counter() >= self.deadline
        ):
            raise StudioStorageError("Billing journal inspection limit exceeded")

    def interrupted(self) -> int:
        return int(time.perf_counter() >= self.deadline)


@dataclass(frozen=True, slots=True)
class _StoredCall:
    identity: str
    state: str
    response: str | None


@dataclass(frozen=True, slots=True)
class BilledEffect:
    """Observed journal metadata, not a provider invoice or publication proof."""

    call_id: str
    job_id: str
    state: str
    reservation_microusd: int


@dataclass(frozen=True, slots=True)
class BillingEffects:
    """Point-in-time pool observation; never authority to release or replay work."""

    job_id: str
    authorization_sha256: str
    pool_limit_microusd: int
    reserved_microusd: int
    effects: tuple[BilledEffect, ...]

    @property
    def outstanding_intents(self) -> tuple[BilledEffect, ...]:
        return tuple(effect for effect in self.effects if effect.state == "intent")


@dataclass(frozen=True, slots=True)
class _BillingSnapshot:
    policies: dict[str, BillingPolicy]
    calls: dict[tuple[str, int], _StoredCall]
    used: dict[str, int]
    effects: tuple[BilledEffect, ...] = ()


def _native_rows(
    db: sqlite3.Connection,
    table: str,
    fields: tuple[tuple[str, int | None, bool], ...],
    budget: _JournalBudget,
    limit: int,
    *,
    count_rows: bool = True,
) -> Iterator[tuple[str | int | None, ...]]:
    # Only fixed schema identifiers reach this projection; values never become SQL.
    projections = []
    for column, ceiling, _ in fields:
        native = (
            f"CASE WHEN typeof({column})='integer' THEN {column} END"
            if ceiling is None
            else f"CASE WHEN typeof({column})='text' "
            f"THEN substr(CAST({column} AS BLOB),1,{ceiling + 1}) END"
        )
        projections.append(f"typeof({column}),length(CAST({column} AS BLOB)),{native}")
    budget.check()
    for index, row in enumerate(
        db.execute(f"SELECT {','.join(projections)} FROM {table} LIMIT ?", (limit + 1,))
    ):
        if index >= limit:
            raise StudioStorageError("Billing journal row limit exceeded")
        budget.check(row=count_rows)
        decoded: list[str | int | None] = []
        for offset, (_, ceiling, nullable) in enumerate(fields):
            kind, size, value = row[offset * 3 : offset * 3 + 3]
            if kind == "null" and nullable and size is None and value is None:
                decoded.append(None)
                continue
            if not _integer(size, 0, budget.max_bytes):
                raise StudioStorageError("Billing journal byte limit or native type invalid")
            budget.check(size=size)
            if ceiling is None:
                if kind != "integer" or type(value) is not int:
                    raise StudioStorageError("Billing reservation native integer evidence changed")
            else:
                if (
                    kind != "text"
                    or not isinstance(value, bytes)
                    or size > ceiling
                    or len(value) != size
                    or b"\0" in value
                ):
                    raise StudioStorageError(
                        "Billing journal complete native text evidence changed"
                    )
                value = value.decode("utf-8", errors="strict")
            decoded.append(value)
        budget.check()
        yield tuple(decoded)


def _inspect_journal(
    db: sqlite3.Connection, job_id: str, policy: BillingPolicy, budget: _JournalBudget
) -> _BillingSnapshot:
    budget.check()
    version = db.execute("PRAGMA user_version").fetchone()[0]
    schema_rows = list(
        _native_rows(
            db,
            "sqlite_schema",
            (
                ("type", 32, False),
                ("name", 512, False),
                ("tbl_name", 512, False),
                ("sql", 8192, True),
            ),
            budget,
            16,
            count_rows=False,
        )
    )
    if version == 0 and not schema_rows:
        return _BillingSnapshot({}, {}, {})
    if version != 1 or len(schema_rows) != len(_SCHEMA) or set(schema_rows) != _SCHEMA:
        raise StudioStorageError("Unsupported billing database schema evidence")
    policies: dict[str, BillingPolicy] = {}
    for identity, raw in _native_rows(
        db, "policies", (("id", 64, False), ("policy_json", 4096, False)), budget, budget.max_rows
    ):
        if (
            not isinstance(identity, str)
            or not _HEX.fullmatch(identity)
            or not isinstance(raw, str)
        ):
            raise StudioStorageError("Billing policy identity evidence changed")
        document = _object(raw, 4096)
        stored = BillingPolicy(**document)
        if (
            stored.authorization_sha256 != identity
            or _canonical(asdict(stored)) != raw
            or identity in policies
        ):
            raise StudioStorageError("Billing pool policy evidence changed")
        policies[identity] = stored
        budget.check()
    supplied = policies.get(policy.authorization_sha256)
    if supplied is not None and supplied != policy:
        raise StudioStorageError(
            "Existing authorization pool policy conflicts with supplied policy"
        )
    calls: dict[tuple[str, int], _StoredCall] = {}
    effects: list[BilledEffect] = []
    used: dict[str, int] = {}
    job_policies: dict[str, str] = {}
    fields = (
        ("id", 64, False),
        ("policy_id", 64, False),
        ("job_id", 71, False),
        ("request_sha256", 64, False),
        ("occurrence", None, False),
        ("input_tokens", None, False),
        ("reservation_microusd", None, False),
        ("state", 9, False),
        ("response_json", _MAX_RESPONSE_BYTES, True),
        ("response_sha256", 64, True),
    )
    for row in _native_rows(db, "calls", fields, budget, budget.max_rows):
        identity, pool, job, request, occurrence, tokens, reservation, state, body, digest = row
        owner = policies.get(pool) if isinstance(pool, str) else None
        if (
            owner is None
            or not isinstance(identity, str)
            or not _HEX.fullmatch(identity)
            or not isinstance(job, str)
            or not re.fullmatch(r"studio-[a-f0-9]{64}", job)
            or not isinstance(request, str)
            or not _HEX.fullmatch(request)
            or not _integer(occurrence, 0, 1_000_000)
            or not _integer(tokens, 0, owner.max_input_tokens)
            or not _integer(reservation, 1, owner.pool_microusd)
        ):
            raise StudioStorageError("Billed reservation identity or arithmetic changed")
        assert isinstance(pool, str) and isinstance(occurrence, int)
        assert isinstance(tokens, int) and isinstance(reservation, int)
        if reservation != owner.reservation(tokens) or identity != _call_id(
            job, request, occurrence, tokens, reservation, pool
        ):
            raise StudioStorageError("Billed reservation identity or arithmetic changed")
        if (job in job_policies and job_policies[job] != pool) or (
            job == job_id and pool != policy.authorization_sha256
        ):
            raise StudioStorageError("Job billing policy identity changed")
        job_policies[job] = pool
        used[pool] = used.get(pool, 0) + reservation
        if used[pool] > owner.pool_microusd:
            raise StudioStorageError("Billed reservation pool evidence exceeds budget")
        if state == "intent":
            if body is not None or digest is not None:
                raise StudioStorageError("Billed intent response evidence changed")
        elif state == "confirmed":
            if (
                not isinstance(body, str)
                or not body
                or not isinstance(digest, str)
                or not _HEX.fullmatch(digest)
                or _digest(body) != digest
            ):
                raise StudioStorageError("Billed response evidence changed or missing")
            _validate_usage(body, tokens, owner)
        else:
            raise StudioStorageError("Billed call state evidence changed")
        if pool == policy.authorization_sha256:
            assert isinstance(state, str)
            effects.append(BilledEffect(identity, job, state, reservation))
        if job == job_id:
            key = (request, occurrence)
            if key in calls:
                raise StudioStorageError("Duplicate billed call identity evidence")
            assert isinstance(state, str) and (body is None or isinstance(body, str))
            calls[key] = _StoredCall(identity, state, body)
        budget.check()
    return _BillingSnapshot(
        policies, calls, used, tuple(sorted(effects, key=lambda item: item.call_id))
    )


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
    def _inspect(
        self,
        db: sqlite3.Connection,
        *,
        max_rows: int = 10_000,
        max_bytes: int = 256 << 20,
        max_seconds: float = 10.0,
        admission: bool = False,
        intent_id: str | None = None,
    ) -> _BillingSnapshot:
        if (
            not _integer(max_rows, 1, 10_000)
            or not _integer(max_bytes, 1, 256 << 20)
            or type(max_seconds) not in (int, float)
            or not 0 < max_seconds <= 10.0
        ):
            raise StudioStorageError("Invalid billing journal inspection limit")
        budget = _JournalBudget(max_rows, max_bytes, time.perf_counter() + max_seconds)
        owns_snapshot = not db.in_transaction
        try:
            budget.check()
            db.set_progress_handler(budget.interrupted, 1000)
            if owns_snapshot:
                db.execute("BEGIN")
            snapshot = _inspect_journal(db, self.job_id, self.policy, budget)
            if admission:
                if self.policy.authorization_sha256 not in snapshot.policies:
                    raise StudioStorageError("Reservation pool policy evidence disappeared")
                intents = [
                    call.identity for call in snapshot.calls.values() if call.state == "intent"
                ]
                if intent_id is not None:
                    if intents != [intent_id]:
                        raise StudioStorageError("Billed intent disappeared or changed")
                elif intents:
                    raise ExternalReconciliationError(
                        "Billed outcome uncertain; attributed provider reconciliation required"
                    )
            budget.check()
            return snapshot
        except (sqlite3.Error, ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise StudioStorageError(
                "Billing journal evidence unavailable, invalid or inspection limit exceeded"
            ) from exc
        finally:
            db.set_progress_handler(None, 0)
            if owns_snapshot and db.in_transaction:
                db.rollback()

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
            self._inspect(db)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            self._inspect(db)
            if db.execute("PRAGMA user_version").fetchone()[0] == 0:
                db.execute(_POLICIES_SQL)
                db.execute(_CALLS_SQL)
                db.execute("PRAGMA user_version=1")
            db.execute(
                "INSERT OR IGNORE INTO policies VALUES (?,?)",
                (policy.authorization_sha256, self._policy_json),
            )
            self._inspect(db)

    @property
    def path(self) -> Path:
        return self._storage.path

    def inspect_effects(
        self,
        *,
        max_rows: int = 10_000,
        max_bytes: int = 256 << 20,
        max_seconds: float = 10.0,
    ) -> BillingEffects:
        """Reopen and validate all rows before exposing selected-pool metadata.

        No egress, response bodies, refunds or logical journal writes. Concurrent
        effects can change after this snapshot; absence of intent is not quiescence.
        """
        with self._lock:
            with self._connection() as db:
                snapshot = self._inspect(
                    db, max_rows=max_rows, max_bytes=max_bytes, max_seconds=max_seconds
                )
                if self.policy.authorization_sha256 not in snapshot.policies:
                    raise StudioStorageError("Reservation pool policy evidence disappeared")
                observed = BillingEffects(
                    self.job_id,
                    self.policy.authorization_sha256,
                    self.policy.pool_microusd,
                    snapshot.used.get(self.policy.authorization_sha256, 0),
                    snapshot.effects,
                )
            return observed

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db: sqlite3.Connection | None = None
        try:
            self._storage.verify()
            db = sqlite3.connect(self.path, timeout=5.0)
            self._storage.verify()
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA trusted_schema=OFF")
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
        snapshot = self._inspect(db, admission=True)
        call = snapshot.calls.get((request_hash, occurrence))
        return call.response if call is not None else None

    def _pool_used(self, db: sqlite3.Connection) -> int:
        snapshot = self._inspect(db, admission=True)
        return snapshot.used.get(self.policy.authorization_sha256, 0)

    def _validate_response(self, body: str, tokens: int) -> None:
        _validate_usage(body, tokens, self.policy)

    def __call__(
        self, url: str, payload: bytes | None, headers: Mapping[str, str]
    ) -> tuple[int, str]:
        with self._lock:
            return self._call(url, payload, headers)

    def _send(
        self,
        url: str,
        payload: bytes | None,
        headers: Mapping[str, str],
        *,
        intent_id: str | None = None,
    ) -> tuple[int, str]:
        with self._connection() as db:
            self._inspect(db, admission=True, intent_id=intent_id)
        if time.time() >= self.policy.expires_at:
            raise ExternalReconciliationError(
                "Spending policy expired before egress; no request sent"
            )
        result = self.upstream(url, payload, headers)
        with self._connection() as db:
            self._inspect(db, admission=True, intent_id=intent_id)
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
        except ExternalReconciliationError:
            raise
        except StudioStorageError as exc:
            raise ExternalReconciliationError(
                "Billing journal refused during count; no generation sent"
            ) from exc
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
            status, body = self._send(url, effective.encode("utf-8"), headers, intent_id=call_id)
            if status != 200:
                raise ValueError("Unconfirmed provider outcome")
            self._validate_response(body, counted)
            with self._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                self._inspect(db, admission=True, intent_id=call_id)
                result = db.execute(
                    "UPDATE calls SET state='confirmed',response_json=?,response_sha256=? "
                    "WHERE id=? AND state='intent'",
                    (body, _digest(body), call_id),
                )
                if result.rowcount != 1:
                    raise StudioStorageError("Billed intent disappeared or changed")
                self._inspect(db, admission=True)
        except Exception as exc:
            raise ExternalReconciliationError(
                "Billed outcome uncertain; response not durably confirmed; "
                "provider reconciliation required"
            ) from exc
        self._occurrences[request_hash] = occurrence + 1
        return 200, body
