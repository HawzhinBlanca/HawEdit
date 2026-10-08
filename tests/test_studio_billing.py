"""Actual SQLite and loopback protocol evidence, not paid-provider acceptance."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from hawedit.gemini import API_ROOT, GeminiJudge, VertexGeminiJudge
from hawedit.studio_billing import BillingPolicy, GuardedGeminiTransport
from hawedit.studio_submissions import StudioStorageError
from hawedit.windows_security import create_private_directory
from hawedit.workflow_recovery import ExternalReconciliationError

BASE = API_ROOT + "/models/gemini-2.5-pro"
VERTEX = "https://aiplatform.googleapis.com/v1/projects/test-project/locations/global/publishers/google/models/gemini-2.5-pro"
JOB = "studio-" + "a" * 64
KEY = "local-protocol-test-not-a-credential"


def policy(base: str = BASE) -> BillingPolicy:
    return BillingPolicy(
        authorization_sha256="b" * 64,
        model_base_url=base,
        expires_at=int(time.time()) + 3600,
        max_input_tokens=200_000,
        max_output_tokens=128,
        thinking_budget=128,
        max_billed_thinking_tokens=32768,
        input_microusd_per_million=1_250_000,
        output_microusd_per_million=10_000_000,
        pool_microusd=10_000_000,
    )


class LocalProtocol:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.generated = 0
        self.drop = False
        self.tokens: object = 10
        self.response: str | Callable[[dict[str, Any]], str] | None = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                document = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.calls.append((self.path, document))
                if self.path == "/countTokens":
                    body = json.dumps({"totalTokens": owner.tokens})
                else:
                    assert self.path == "/generateContent"
                    owner.generated += 1
                    if owner.drop:
                        self.connection.shutdown(socket.SHUT_RDWR)
                        self.connection.close()
                        return
                    configured = owner.response
                    body = (
                        configured(document) if callable(configured) else configured
                    ) or json.dumps(
                        {
                            "candidates": [
                                {"content": {"parts": [{"text": '{"candidates": []}'}]}}
                            ],
                            "usageMetadata": {
                                "promptTokenCount": 10,
                                "candidatesTokenCount": 5,
                                "thoughtsTokenCount": 4,
                                "totalTokenCount": 19,
                            },
                            "responseId": str(owner.generated),
                        }
                    )
                data = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def transport(
        self, url: str, body: bytes | None, headers: Mapping[str, str]
    ) -> tuple[int, str]:
        method = url.rsplit(":", 1)[1]
        local = f"http://127.0.0.1:{self.server.server_port}/{method}"
        request = urllib.request.Request(local, data=body, headers=dict(headers))
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, response.read((1 << 20) + 1).decode("utf-8")

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        assert not self.thread.is_alive()


@pytest.fixture
def api() -> Iterator[LocalProtocol]:
    local = LocalProtocol()
    try:
        yield local
    finally:
        local.close()


def guard(
    tmp_path: Path, api: LocalProtocol, p: BillingPolicy | None = None, job: str = JOB
) -> GuardedGeminiTransport:
    return GuardedGeminiTransport(private_billing_path(tmp_path), job, p or policy(), api.transport)


def private_billing_path(tmp_path: Path) -> Path:
    directory = tmp_path / "private-billing"
    if not directory.exists():
        if os.name == "nt":
            create_private_directory(directory)
        else:
            directory.mkdir(mode=0o700)
    return directory / "billing.sqlite3"


def seed_private_file(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def payload(text: str = "local protocol input") -> bytes:
    return json.dumps(
        {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {"type": "object"},
                "temperature": 0.0,
            },
        }
    ).encode()


def test_studio_effects_empty_observation_is_read_only(tmp_path: Path, api: LocalProtocol) -> None:
    client = guard(tmp_path, api)
    with sqlite3.connect(client.path) as db:
        before = tuple(db.iterdump())
    observed = client.inspect_effects()
    assert observed.job_id == JOB
    assert observed.authorization_sha256 == client.policy.authorization_sha256
    assert observed.reserved_microusd == 0
    assert observed.pool_limit_microusd == client.policy.pool_microusd
    assert observed.effects == observed.outstanding_intents == ()
    assert api.calls == []
    with sqlite3.connect(client.path) as db:
        assert tuple(db.iterdump()) == before


def test_studio_effects_confirmed_metadata_is_not_response_or_invoice(
    tmp_path: Path, api: LocalProtocol
) -> None:
    client = guard(tmp_path, api)
    for _ in range(2):
        client(BASE + ":generateContent", payload("private-never-returned-text"), {})
    routes = tuple(api.calls)
    observed = client.inspect_effects()
    assert observed.reserved_microusd == 2 * client.policy.reservation(10)
    assert len(observed.effects) == 2
    assert len({effect.call_id for effect in observed.effects}) == 2
    assert {effect.state for effect in observed.effects} == {"confirmed"}
    assert {effect.job_id for effect in observed.effects} == {JOB}
    assert observed.outstanding_intents == ()
    raw = json.dumps(asdict(observed))
    assert "private-never-returned-text" not in raw
    assert "response_json" not in raw and "usageMetadata" not in raw
    assert not hasattr(observed, "invoice_microusd")
    assert not hasattr(observed, "publication_verified")
    assert tuple(api.calls) == routes
    assert client.inspect_effects() == observed


def test_studio_effects_uncertainty_is_observed_without_replay(
    tmp_path: Path, api: LocalProtocol
) -> None:
    client = guard(tmp_path, api)
    api.drop = True
    with pytest.raises(ExternalReconciliationError):
        client(BASE + ":generateContent", payload(), {})
    routes = tuple(api.calls)
    with sqlite3.connect(client.path) as db:
        before = tuple(db.iterdump())
    observed = client.inspect_effects()
    assert len(observed.effects) == len(observed.outstanding_intents) == 1
    assert observed.outstanding_intents[0].state == "intent"
    assert observed.reserved_microusd == client.policy.reservation(10)
    assert client.inspect_effects() == observed
    assert tuple(api.calls) == routes
    with sqlite3.connect(client.path) as db:
        assert tuple(db.iterdump()) == before


def test_studio_effects_includes_other_job_uncertainty(tmp_path: Path, api: LocalProtocol) -> None:
    p = policy()
    original = guard(tmp_path, api, p)
    api.drop = True
    with pytest.raises(ExternalReconciliationError):
        original(BASE + ":generateContent", payload(), {})
    other = guard(tmp_path, api, p, "studio-" + "c" * 64)
    routes = tuple(api.calls)
    observed = other.inspect_effects()
    assert observed.job_id == other.job_id
    assert {effect.job_id for effect in observed.outstanding_intents} == {JOB}
    assert observed.reserved_microusd == p.reservation(10)
    assert tuple(api.calls) == routes


def test_studio_effects_filters_only_after_validation(tmp_path: Path, api: LocalProtocol) -> None:
    p = policy()
    original = guard(tmp_path, api, p)
    api.drop = True
    with pytest.raises(ExternalReconciliationError):
        original(BASE + ":generateContent", payload(), {})
    separate = guard(tmp_path, api, replace(p, authorization_sha256="d" * 64), "studio-" + "e" * 64)
    observed = separate.inspect_effects()
    assert observed.effects == observed.outstanding_intents == ()
    assert observed.reserved_microusd == 0
    assert len(original.inspect_effects().outstanding_intents) == 1


def test_studio_effects_refuses_corrupt_foreign_rows(tmp_path: Path, api: LocalProtocol) -> None:
    p = policy()
    original = guard(tmp_path, api, p)
    original(BASE + ":generateContent", payload(), {})
    separate = guard(tmp_path, api, replace(p, authorization_sha256="d" * 64), "studio-" + "e" * 64)
    with sqlite3.connect(original.path) as db:
        db.execute("UPDATE calls SET reservation_microusd=reservation_microusd+1")
        db.commit()
        before = tuple(db.iterdump())
    routes = tuple(api.calls)
    with pytest.raises(StudioStorageError, match="arithmetic"):
        separate.inspect_effects()
    assert tuple(api.calls) == routes
    with sqlite3.connect(original.path) as db:
        assert tuple(db.iterdump()) == before


def test_studio_effects_refuses_changed_database_identity(
    tmp_path: Path, api: LocalProtocol
) -> None:
    client = guard(tmp_path, api)
    preserved = client.path.with_name("retained.sqlite3")
    client.path.rename(preserved)
    seed_private_file(client.path, b"replacement, not the original journal")
    with pytest.raises(StudioStorageError, match="identity|binding"):
        client.inspect_effects()
    assert api.calls == []
    assert client.path.read_bytes() == b"replacement, not the original journal"
    assert preserved.is_file()


def test_studio_effects_bounded_inspection_preserves_evidence(
    tmp_path: Path, api: LocalProtocol
) -> None:
    client = guard(tmp_path, api)
    client(BASE + ":generateContent", payload(), {})
    with sqlite3.connect(client.path) as db:
        before = tuple(db.iterdump())
    routes = tuple(api.calls)
    with pytest.raises(StudioStorageError, match="limit"):
        client.inspect_effects(max_rows=1)
    assert tuple(api.calls) == routes
    with sqlite3.connect(client.path) as db:
        assert tuple(db.iterdump()) == before


def test_studio_billing_repeated_content_preserves_occurrences(
    tmp_path: Path, api: LocalProtocol
) -> None:
    p = policy()
    first = guard(tmp_path, api, p)
    responses = [
        first(BASE + ":generateContent", payload(), {"x-goog-api-key": KEY}) for _ in range(5)
    ]
    assert api.generated == 5
    assert len({body for _, body in responses}) == 5
    replay = guard(tmp_path, api, p)
    before = len(api.calls)
    assert [replay(BASE + ":generateContent", payload(), {}) for _ in range(5)] == responses
    assert len(api.calls) == before
    with sqlite3.connect(private_billing_path(tmp_path)) as db:
        rows = db.execute(
            "SELECT occurrence, state, reservation_microusd FROM calls ORDER BY occurrence"
        ).fetchall()
    assert rows == [(i, "confirmed", 328973) for i in range(5)]
    assert KEY.encode() not in private_billing_path(tmp_path).read_bytes()


@pytest.mark.parametrize("base", [BASE, VERTEX])
def test_studio_billing_counts_full_capped_configuration(
    tmp_path: Path, api: LocalProtocol, base: str
) -> None:
    guarded = guard(tmp_path, api, policy(base))
    if base == BASE:
        client = GeminiJudge(api_key=KEY, transport=guarded)
    else:
        client = VertexGeminiJudge("test-project", token_provider=lambda: KEY, transport=guarded)
    client.generate_json([{"text": "local protocol"}], {"type": "object"})
    count = api.calls[0][1]
    generation = api.calls[1][1]
    counted = count["generateContentRequest"] if base == BASE else count
    assert counted["contents"] == generation["contents"]
    assert counted["generationConfig"] == generation["generationConfig"]
    assert generation["generationConfig"]["maxOutputTokens"] == 128
    assert generation["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 128}
    assert generation["generationConfig"]["candidateCount"] == 1


def test_studio_billing_response_loss_refuses_replay(tmp_path: Path, api: LocalProtocol) -> None:
    p = policy()
    api.drop = True
    with pytest.raises(ExternalReconciliationError, match="uncertain"):
        guard(tmp_path, api, p)(BASE + ":generateContent", payload(), {})
    assert api.generated == 1
    api.drop = False
    for body in (payload(), payload("different content cannot bypass uncertainty")):
        with pytest.raises(ExternalReconciliationError, match="reconciliation"):
            guard(tmp_path, api, p)(BASE + ":generateContent", body, {})
    assert api.generated == 1
    assert len(api.calls) == 2


@pytest.mark.parametrize("operation", ["INSERT", "UPDATE"])
def test_studio_billing_storage_failures_are_atomic(
    tmp_path: Path, api: LocalProtocol, operation: str
) -> None:
    p = policy()
    guarded = guard(tmp_path, api, p)

    def inject_outage(document: dict[str, Any]) -> str:
        with sqlite3.connect(private_billing_path(tmp_path)) as db:
            db.execute(
                f"CREATE TRIGGER outage BEFORE {operation} ON calls "
                "BEGIN SELECT RAISE(ABORT, 'actual storage outage'); END"
            )
        return ""

    if operation == "INSERT":
        inject_outage({})
    else:
        # Keep an actual response-time storage failure after one native HTTP generation.
        api.response = inject_outage
    expected = StudioStorageError if operation == "INSERT" else ExternalReconciliationError
    with pytest.raises(expected):
        guarded(BASE + ":generateContent", payload(), {})
    assert api.generated == (0 if operation == "INSERT" else 1)
    with sqlite3.connect(private_billing_path(tmp_path)) as db:
        db.execute("DROP TRIGGER outage")
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone() == (
            (0,) if operation == "INSERT" else (1,)
        )
    if operation == "UPDATE":
        with pytest.raises(ExternalReconciliationError):
            guard(tmp_path, api, p)(BASE + ":generateContent", payload(), {})
        assert api.generated == 1


def test_studio_billing_pool_is_shared_and_never_refunded(
    tmp_path: Path, api: LocalProtocol
) -> None:
    p = replace(policy(), pool_microusd=328973)
    guard(tmp_path, api, p)(BASE + ":generateContent", payload(), {})
    with pytest.raises(ExternalReconciliationError, match="budget"):
        guard(tmp_path, api, p, "studio-" + "c" * 64)(BASE + ":generateContent", payload(), {})
    assert api.generated == 1


def test_studio_billing_policy_drift_is_refused(tmp_path: Path, api: LocalProtocol) -> None:
    p = policy()
    guard(tmp_path, api, p)
    with pytest.raises(StudioStorageError, match="policy"):
        guard(tmp_path, api, replace(p, pool_microusd=p.pool_microusd + 1))
    assert api.calls == []


@pytest.mark.parametrize("tokens", [True, -1, 200001, "10"])
def test_studio_billing_invalid_provider_count_cannot_generate(
    tmp_path: Path, api: LocalProtocol, tokens: object
) -> None:
    api.tokens = tokens
    with pytest.raises(ExternalReconciliationError, match="count"):
        guard(tmp_path, api)(BASE + ":generateContent", payload(), {})
    assert api.generated == 0


@pytest.mark.parametrize(
    "url",
    [
        BASE + ":generateContent?key=bad",
        BASE.replace("2.5", "3.1") + ":generateContent",
        "http://127.0.0.1/generateContent",
    ],
)
def test_studio_billing_unapproved_route_never_egresses(
    tmp_path: Path, api: LocalProtocol, url: str
) -> None:
    with pytest.raises(ExternalReconciliationError, match="route"):
        guard(tmp_path, api)(url, payload(), {})
    assert api.calls == []


@pytest.mark.parametrize(
    "change",
    [
        {"tools": []},
        {"generationConfig": {"candidateCount": 2}},
        {"generationConfig": {"maxOutputTokens": 999}},
        {"generationConfig": {"thinkingConfig": {"thinkingBudget": -1}}},
    ],
)
def test_studio_billing_unpriced_or_conflicting_options_refuse_egress(
    tmp_path: Path, api: LocalProtocol, change: dict[str, Any]
) -> None:
    document = json.loads(payload())
    document.update(change)
    with pytest.raises(ExternalReconciliationError):
        guard(tmp_path, api)(BASE + ":generateContent", json.dumps(document).encode(), {})
    assert api.calls == []


def test_studio_billing_expired_policy_cannot_count_or_generate(
    tmp_path: Path, api: LocalProtocol
) -> None:
    guarded = guard(tmp_path, api, replace(policy(), expires_at=int(time.time()) - 1))
    for method, body in (("countTokens", b'{"contents": []}'), ("generateContent", payload())):
        with pytest.raises(ExternalReconciliationError, match="expired"):
            guarded(BASE + ":" + method, body, {})
    assert api.calls == []


def test_studio_billing_changed_response_is_not_replayed(
    tmp_path: Path, api: LocalProtocol
) -> None:
    p = policy()
    guard(tmp_path, api, p)(BASE + ":generateContent", payload(), {})
    with sqlite3.connect(private_billing_path(tmp_path)) as db:
        db.execute("UPDATE calls SET response_json='{}'")
    with pytest.raises(StudioStorageError, match="response"):
        guard(tmp_path, api, p)(BASE + ":generateContent", payload(), {})
    assert api.generated == 1


@pytest.mark.parametrize(
    "response",
    [
        "{}",
        '{"usageMetadata":{"promptTokenCount":true}}',
        '{"usageMetadata":{"promptTokenCount":10,"candidatesTokenCount":99999,"thoughtsTokenCount":0,"totalTokenCount":100009}}',
    ],
)
def test_studio_billing_missing_or_excess_usage_stays_uncertain(
    tmp_path: Path, api: LocalProtocol, response: str
) -> None:
    p = policy()
    api.response = response
    with pytest.raises(ExternalReconciliationError):
        guard(tmp_path, api, p)(BASE + ":generateContent", payload(), {})
    with pytest.raises(ExternalReconciliationError):
        guard(tmp_path, api, p)(BASE + ":generateContent", payload(), {})
    assert api.generated == 1


def test_studio_builder_routes_discovery_through_injected_transport(
    tmp_path: Path, api: LocalProtocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.pipeline import StageSkipped, build_and_run, build_parser
    from test_pipeline import FIXTURE, a_transcript

    transcript = tmp_path / "transcript.json"
    transcript.write_text(a_transcript(FIXTURE.stem).to_json(), encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    p = policy()
    args = build_parser().parse_args(
        [
            str(FIXTURE),
            "--transcript",
            str(transcript),
            "--gemini",
            "--auto-select",
            "--work-dir",
            str(tmp_path / "work"),
        ]
    )
    result = build_and_run(args, judge_transport=guard(tmp_path, api, p))
    assert api.generated == 5
    assert result.clip is None
    assert isinstance(result.render, StageSkipped)
    assert "QC" in result.render.reason
    assert (
        hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == a_transcript(FIXTURE.stem).media_sha256
    )


def test_studio_builder_routes_judging_with_real_frames_through_injected_transport(
    tmp_path: Path, api: LocalProtocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.pipeline import StageSkipped, build_and_run, build_parser
    from test_gemini import verdict_fields
    from test_pipeline import FIXTURE, a_transcript

    transcript = tmp_path / "transcript.json"
    transcript.write_text(a_transcript(FIXTURE.stem).to_json(), encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", KEY)

    def response(document: dict[str, Any]) -> str:
        schema = document["generationConfig"]["responseSchema"]
        fields = verdict_fields(payoff_at_ms=1000)
        if "candidates" in schema["properties"]:
            fields = {
                "candidates": [
                    {"in_ms": 100, "out_ms": 1700, "score": 0.9, "reason_ckb": fields["reason_ckb"]}
                ]
            }
        return json.dumps(
            {
                "candidates": [{"content": {"parts": [{"text": json.dumps(fields)}]}}],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 5,
                    "thoughtsTokenCount": 4,
                    "totalTokenCount": 19,
                },
            }
        )

    api.response = response
    args = build_parser().parse_args(
        [
            str(FIXTURE),
            "--transcript",
            str(transcript),
            "--gemini",
            "--sentences",
            "0",
            "--work-dir",
            str(tmp_path / "work"),
        ]
    )
    result = build_and_run(args, judge_transport=guard(tmp_path, api))
    assert api.generated == 6
    assert result.editorial is None
    assert result.clip is not None and result.clip.editorial is not None
    assert isinstance(result.delivery, StageSkipped)
    parts = next(
        document["contents"][0]["parts"]
        for method, document in api.calls
        if method == "/generateContent"
        and any("inlineData" in part for part in document["contents"][0]["parts"])
    )
    assert any("inlineData" in part for part in parts)


def test_studio_billing_corrupt_reservation_cannot_restore_budget(
    tmp_path: Path, api: LocalProtocol
) -> None:
    p = replace(policy(), pool_microusd=2 * 328973)
    guard(tmp_path, api, p)(BASE + ":generateContent", payload(), {})
    with sqlite3.connect(private_billing_path(tmp_path)) as db:
        db.execute("UPDATE calls SET reservation_microusd=1")
    with pytest.raises(StudioStorageError, match="reservation"):
        guard(tmp_path, api, p, "studio-" + "c" * 64)(
            BASE + ":generateContent", payload("another job"), {}
        )
    assert api.generated == 1


def test_studio_billing_existing_job_cannot_change_authorization(
    tmp_path: Path, api: LocalProtocol
) -> None:
    p = policy()
    guard(tmp_path, api, p)(BASE + ":generateContent", payload(), {})
    with pytest.raises(StudioStorageError, match="policy"):
        guard(tmp_path, api, replace(p, authorization_sha256="d" * 64))(
            BASE + ":generateContent", payload("different"), {}
        )
    assert api.generated == 1


def test_studio_billing_expiry_during_count_prevents_generation(
    tmp_path: Path, api: LocalProtocol
) -> None:
    p = replace(policy(), expires_at=int(time.time()) + 1)

    def slow_count(url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        result = api.transport(url, body, headers)
        if url.endswith(":countTokens"):
            time.sleep(max(0, p.expires_at - time.time()) + 0.05)
        return result

    guarded = GuardedGeminiTransport(private_billing_path(tmp_path), JOB, p, slow_count)
    with pytest.raises(ExternalReconciliationError, match="expired"):
        guarded(BASE + ":generateContent", payload(), {})
    assert api.generated == 0


def test_studio_billing_private_root_required_before_any_egress(
    tmp_path: Path, api: LocalProtocol
) -> None:
    directory = tmp_path / "ordinary-inherited-root"
    directory.mkdir()
    if os.name != "nt":
        directory.chmod(0o755)
    path = directory / "billing.sqlite3"
    with pytest.raises(StudioStorageError, match="private"):
        GuardedGeminiTransport(path, JOB, policy(), api.transport)
    assert not path.exists()
    assert api.calls == []


def test_studio_billing_linked_database_refused(tmp_path: Path, api: LocalProtocol) -> None:
    path = private_billing_path(tmp_path)
    GuardedGeminiTransport(path, JOB, policy(), api.transport)
    alias = tmp_path / "outside-journal.sqlite3"
    os.link(path, alias)
    before = path.read_bytes()
    with pytest.raises(StudioStorageError, match="linked|private"):
        GuardedGeminiTransport(path, JOB, policy(), api.transport)
    assert path.read_bytes() == alias.read_bytes() == before
    assert api.calls == []


def test_studio_billing_database_replacement_during_count_refuses_generation(
    tmp_path: Path, api: LocalProtocol
) -> None:
    path = private_billing_path(tmp_path)

    def replace_after_count(
        url: str, body: bytes | None, headers: Mapping[str, str]
    ) -> tuple[int, str]:
        result = api.transport(url, body, headers)
        if url.endswith(":countTokens"):
            clone = path.with_name("replacement.sqlite3")
            seed_private_file(clone, path.read_bytes())
            os.replace(clone, path)
        return result

    guarded = GuardedGeminiTransport(path, JOB, policy(), replace_after_count)
    with pytest.raises(ExternalReconciliationError, match="count|private|changed"):
        guarded(BASE + ":generateContent", payload(), {})
    assert [name for name, _ in api.calls] == ["/countTokens"]
    assert api.generated == 0


def test_studio_billing_root_replacement_after_response_retains_uncertainty(
    tmp_path: Path, api: LocalProtocol
) -> None:
    path = private_billing_path(tmp_path)
    retained = tmp_path / "retained-private-billing"
    p = policy()

    def replace_after_generation(
        url: str, body: bytes | None, headers: Mapping[str, str]
    ) -> tuple[int, str]:
        result = api.transport(url, body, headers)
        if url.endswith(":generateContent"):
            assert path.parent.parent.resolve() == retained.parent.resolve() == tmp_path.resolve()
            path.parent.rename(retained)
            path.parent.mkdir()
            seed_private_file(path, (retained / path.name).read_bytes())
        return result

    guarded = GuardedGeminiTransport(path, JOB, p, replace_after_generation)
    with pytest.raises(ExternalReconciliationError, match="uncertain|private|changed"):
        guarded(BASE + ":generateContent", payload(), {})
    with sqlite3.connect(retained / path.name) as db:
        assert db.execute("SELECT state,response_json FROM calls").fetchall() == [("intent", None)]
    assert api.generated == 1
    with pytest.raises(ExternalReconciliationError, match="reconciliation"):
        GuardedGeminiTransport(retained / path.name, JOB, p, api.transport)(
            BASE + ":generateContent", payload(), {}
        )
    assert api.generated == 1


@pytest.mark.parametrize("method", ["countTokens", "generateContent"])
def test_studio_billing_storage_drift_refuses_both_egress_routes(
    tmp_path: Path, api: LocalProtocol, method: str
) -> None:
    guarded = guard(tmp_path, api)
    os.link(guarded.path, tmp_path / "outside-journal.sqlite3")
    body = b'{"contents":[{"parts":[{"text":"private test input"}]}]}'
    with pytest.raises(StudioStorageError, match="linked|private"):
        guarded(BASE + ":" + method, body if method == "countTokens" else payload(), {})
    assert api.calls == []


def test_studio_billing_process_crash_after_response_refuses_replay(
    tmp_path: Path, api: LocalProtocol
) -> None:
    from dataclasses import asdict

    p = policy()
    program = """
import json, os, sys, urllib.request
from pathlib import Path
from hawedit.studio_billing import BillingPolicy, GuardedGeminiTransport
path, job, policy_json, port, request = sys.argv[1:]
p = BillingPolicy(**json.loads(policy_json))
def transport(url, body, headers):
    method = url.rsplit(':', 1)[1]
    req = urllib.request.Request('http://127.0.0.1:'+port+'/'+method, data=body)
    with urllib.request.urlopen(req, timeout=3) as response:
        result = response.status, response.read(1048577).decode('utf-8')
    if method == 'generateContent':
        os._exit(23)
    return result
GuardedGeminiTransport(Path(path), job, p, transport)(
    p.model_base_url+':generateContent', request.encode(), {})
"""
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            program,
            str(private_billing_path(tmp_path)),
            JOB,
            json.dumps(asdict(p)),
            str(api.server.server_port),
            payload().decode(),
        ],
        capture_output=True,
        timeout=15,
    )
    assert done.returncode == 23, done.stderr.decode("utf-8", "replace")
    assert api.generated == 1
    with pytest.raises(ExternalReconciliationError, match="reconciliation"):
        guard(tmp_path, api, p)(BASE + ":generateContent", payload(), {})
    assert api.generated == 1


@pytest.mark.parametrize("damage", ["version", "foreign", "foreign-version-one", "not-database"])
def test_studio_billing_unrecognized_storage_is_preserved(
    tmp_path: Path, api: LocalProtocol, damage: str
) -> None:
    path = private_billing_path(tmp_path)
    seed_private_file(path, b"")
    if damage == "not-database":
        path.write_bytes(b"not a database")
    else:
        with sqlite3.connect(path) as db:
            db.execute(
                "PRAGMA user_version=2"
                if damage == "version"
                else "CREATE TABLE foreign_data(value)"
            )
            if damage == "foreign-version-one":
                db.execute("PRAGMA user_version=1")
    before = path.read_bytes()
    with pytest.raises(StudioStorageError):
        guard(tmp_path, api)
    assert path.read_bytes() == before
    assert api.calls == []


def test_studio_billing_concurrent_jobs_cannot_oversubscribe_pool(
    tmp_path: Path, api: LocalProtocol
) -> None:
    p = replace(policy(), pool_microusd=328973)
    guards = [guard(tmp_path, api, p, "studio-" + char * 64) for char in ("a", "c")]
    barrier = threading.Barrier(2)

    def run(index: int) -> str:
        barrier.wait(timeout=5)
        try:
            guards[index](BASE + ":generateContent", payload(str(index)), {})
            return "confirmed"
        except ExternalReconciliationError as exc:
            assert "budget" in str(exc)
            return "refused"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, (0, 1)))
    assert sorted(results) == ["confirmed", "refused"]
    assert api.generated == 1


@pytest.mark.parametrize(
    "body",
    [b'{"contents":[],"contents":[]}', b"[" * 16384 + b"0" + b"]" * 16384, b" " * ((16 << 20) + 1)],
    ids=["duplicate-keys", "native-depth", "over-byte-limit"],
)
def test_studio_billing_malformed_bounded_request_refuses_egress(
    tmp_path: Path, api: LocalProtocol, body: bytes
) -> None:
    with pytest.raises(ExternalReconciliationError):
        guard(tmp_path, api)(BASE + ":generateContent", body, {})
    assert api.calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("authorization_sha256", True),
        ("model_base_url", True),
        ("max_input_tokens", True),
        ("thinking_budget", -1),
        ("input_microusd_per_million", 0),
        ("pool_microusd", -1),
    ],
    ids=[
        "digest-boolean",
        "route-boolean",
        "input-boolean",
        "dynamic-thinking",
        "unpriced-input",
        "negative-budget",
    ],
)
def test_studio_billing_policy_fields_are_strict(field: str, value: object) -> None:
    from dataclasses import asdict

    fields = asdict(policy())
    fields[field] = value
    with pytest.raises(ValueError):
        BillingPolicy(**fields)


def _billing_bytes(path: Path) -> tuple[object, ...]:
    with sqlite3.connect(path) as db:
        records: list[object] = [
            db.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
            ).fetchall()
        ]
        for table, columns in (
            ("policies", ("id", "policy_json")),
            (
                "calls",
                (
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
            ),
        ):
            projection = ",".join(f"typeof({column}),CAST({column} AS BLOB)" for column in columns)
            records.append(
                db.execute(f"SELECT {projection} FROM {table} ORDER BY rowid").fetchall()
            )
        return tuple(records)


def _count_payload() -> bytes:
    return json.dumps({"contents": [{"parts": [{"text": "local count"}]}]}).encode()


@pytest.mark.parametrize("route", ["adopt", "countTokens", "generateContent"])
def test_studio_billing_policy_projection_suffix_refused(
    tmp_path: Path, api: LocalProtocol, route: str
) -> None:
    p = policy()
    guarded = guard(tmp_path, api, p)
    with sqlite3.connect(guarded.path) as db:
        db.execute("UPDATE policies SET policy_json=policy_json||char(0)||'hidden'")
    before = _billing_bytes(guarded.path)
    with pytest.raises(StudioStorageError):
        if route == "adopt":
            guard(tmp_path, api, p)
        else:
            guarded(
                BASE + ":" + route, _count_payload() if route == "countTokens" else payload(), {}
            )
    assert api.calls == []
    assert _billing_bytes(guarded.path) == before


@pytest.mark.parametrize("field", ["id", "policy_id", "job_id", "request_sha256", "state"])
@pytest.mark.parametrize("route", ["countTokens", "generateContent"])
def test_studio_billing_hidden_intent_cannot_escape_admission(
    tmp_path: Path, api: LocalProtocol, field: str, route: str
) -> None:
    guarded = guard(tmp_path, api)
    api.drop = True
    with pytest.raises(ExternalReconciliationError):
        guarded(BASE + ":generateContent", payload(), {})
    api.drop = False
    with sqlite3.connect(guarded.path) as db:
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute(f"UPDATE calls SET {field}={field}||char(0)||'hidden'")
    before = _billing_bytes(guarded.path)
    requests = len(api.calls)
    with pytest.raises(StudioStorageError):
        guarded(
            BASE + ":" + route,
            _count_payload() if route == "countTokens" else payload("changed request"),
            {},
        )
    assert api.generated == 1 and len(api.calls) == requests
    assert _billing_bytes(guarded.path) == before


@pytest.mark.parametrize("route", ["adopt", "countTokens", "generateContent"])
def test_studio_billing_response_projection_suffix_refused(
    tmp_path: Path, api: LocalProtocol, route: str
) -> None:
    p = policy()
    guard(tmp_path, api, p)(BASE + ":generateContent", payload(), {})
    replay = guard(tmp_path, api, p)
    with sqlite3.connect(replay.path) as db:
        db.execute("UPDATE calls SET response_json=response_json||char(0)||'hidden'")
    before = _billing_bytes(replay.path)
    requests = len(api.calls)
    with pytest.raises(StudioStorageError):
        if route == "adopt":
            guard(tmp_path, api, p)
        else:
            replay(
                BASE + ":" + route, _count_payload() if route == "countTokens" else payload(), {}
            )
    assert len(api.calls) == requests and api.generated == 1
    assert _billing_bytes(replay.path) == before


@pytest.mark.parametrize(
    "damage",
    [
        "view",
        "index",
        "column",
        "null-key",
        "blob-policy",
        "invalid-utf8",
        "oversize",
        "scalar-type",
    ],
)
@pytest.mark.parametrize("route", ["adopt", "countTokens"])
def test_studio_billing_native_admission_refuses_foreign_storage(
    tmp_path: Path, api: LocalProtocol, damage: str, route: str
) -> None:
    p = policy()
    guarded = guard(tmp_path, api, p)
    if damage == "scalar-type":
        guarded(BASE + ":generateContent", payload(), {})
    with sqlite3.connect(guarded.path) as db:
        statements = {
            "view": "CREATE VIEW foreign_view AS SELECT 1",
            "index": "CREATE INDEX foreign_index ON policies(policy_json)",
            "column": "ALTER TABLE policies ADD COLUMN foreign_value TEXT",
            "null-key": "INSERT INTO policies SELECT NULL,policy_json FROM policies LIMIT 1",
            "blob-policy": "UPDATE policies SET policy_json=CAST(policy_json AS BLOB)",
            "invalid-utf8": "UPDATE policies SET policy_json=CAST(x'fffe' AS TEXT)",
            "oversize": "UPDATE policies SET policy_json=policy_json||zeroblob(4097)",
            "scalar-type": "UPDATE calls SET occurrence='not-an-integer'",
        }
        db.execute(statements[damage])
    before = _billing_bytes(guarded.path)
    requests = len(api.calls)
    with pytest.raises(StudioStorageError):
        if route == "adopt":
            guard(tmp_path, api, p)
        else:
            guarded(BASE + ":countTokens", _count_payload(), {})
    assert len(api.calls) == requests
    assert _billing_bytes(guarded.path) == before


@pytest.mark.parametrize("damage", ["policy", "response"])
@pytest.mark.parametrize("route", ["countTokens", "generateContent"])
def test_studio_billing_admission_audits_foreign_pool_rows(
    tmp_path: Path, api: LocalProtocol, damage: str, route: str
) -> None:
    p = policy()
    guard(tmp_path, api, p)(BASE + ":generateContent", payload(), {})
    current = guard(tmp_path, api, p)
    other = replace(p, authorization_sha256="c" * 64, max_output_tokens=8)
    guard(tmp_path, api, other, "studio-" + "d" * 64)(BASE + ":generateContent", payload(), {})
    with sqlite3.connect(current.path) as db:
        if damage == "policy":
            db.execute(
                "UPDATE policies SET policy_json=policy_json||char(0)||'hidden' WHERE id=?",
                (other.authorization_sha256,),
            )
        else:
            raw = db.execute(
                "SELECT response_json FROM calls WHERE policy_id=?", (other.authorization_sha256,)
            ).fetchone()[0]
            document = json.loads(raw)
            document["usageMetadata"].update(candidatesTokenCount=64, totalTokenCount=78)
            changed = json.dumps(document)
            db.execute(
                "UPDATE calls SET response_json=?,response_sha256=? WHERE policy_id=?",
                (changed, hashlib.sha256(changed.encode()).hexdigest(), other.authorization_sha256),
            )
    before = _billing_bytes(current.path)
    requests = len(api.calls)
    with pytest.raises(StudioStorageError):
        current(BASE + ":" + route, _count_payload() if route == "countTokens" else payload(), {})
    assert len(api.calls) == requests and api.generated == 2
    assert _billing_bytes(current.path) == before


def test_studio_billing_journal_drift_during_count_prevents_generation(
    tmp_path: Path, api: LocalProtocol
) -> None:
    path = private_billing_path(tmp_path)

    def change_after_count(
        url: str, body: bytes | None, headers: Mapping[str, str]
    ) -> tuple[int, str]:
        response = api.transport(url, body, headers)
        if url.endswith(":countTokens"):
            with sqlite3.connect(path) as db:
                db.execute("UPDATE policies SET policy_json=policy_json||char(0)||'hidden'")
        return response

    guarded = GuardedGeminiTransport(path, JOB, policy(), change_after_count)
    with pytest.raises(ExternalReconciliationError, match="count"):
        guarded(BASE + ":generateContent", payload(), {})
    assert [route for route, _ in api.calls] == ["/countTokens"]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 0
        assert (
            b"\x00hidden"
            in db.execute("SELECT CAST(policy_json AS BLOB) FROM policies").fetchone()[0]
        )


@pytest.mark.parametrize("damage", ["policy", "view"])
def test_studio_billing_direct_count_refuses_invalid_journal(
    tmp_path: Path, api: LocalProtocol, damage: str
) -> None:
    guarded = guard(tmp_path, api)
    with sqlite3.connect(guarded.path) as db:
        db.execute(
            "UPDATE policies SET policy_json='{}'"
            if damage == "policy"
            else "CREATE VIEW foreign_view AS SELECT 1"
        )
    before = _billing_bytes(guarded.path)
    with pytest.raises(StudioStorageError):
        guarded(BASE + ":countTokens", _count_payload(), {})
    assert api.calls == [] and _billing_bytes(guarded.path) == before


def test_studio_billing_confirmation_drift_stays_uncertain(
    tmp_path: Path, api: LocalProtocol
) -> None:
    path = private_billing_path(tmp_path)
    changed: list[tuple[object, ...]] = []

    def change_after_generation(
        url: str, body: bytes | None, headers: Mapping[str, str]
    ) -> tuple[int, str]:
        response = api.transport(url, body, headers)
        if url.endswith(":generateContent"):
            with sqlite3.connect(path) as db:
                db.execute("UPDATE calls SET job_id=job_id||char(0)||'hidden'")
            changed.append(_billing_bytes(path))
        return response

    guarded = GuardedGeminiTransport(path, JOB, policy(), change_after_generation)
    with pytest.raises(ExternalReconciliationError, match="uncertain"):
        guarded(BASE + ":generateContent", payload(), {})
    assert api.generated == 1 and _billing_bytes(path) == changed[0]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT state,response_json FROM calls").fetchall() == [("intent", None)]
    requests = len(api.calls)
    with pytest.raises(StudioStorageError):
        guarded(BASE + ":generateContent", payload("changed"), {})
    assert api.generated == 1 and len(api.calls) == requests


def test_studio_billing_valid_multiple_pools_remain_usable(
    tmp_path: Path, api: LocalProtocol
) -> None:
    first = policy()
    second = replace(
        first, authorization_sha256="c" * 64, max_output_tokens=8, max_billed_thinking_tokens=128
    )
    responses = []
    for p, job in ((first, JOB), (second, "studio-" + "d" * 64)):
        responses.append(guard(tmp_path, api, p, job)(BASE + ":generateContent", payload(), {}))
    requests = len(api.calls)
    for index, (p, job) in enumerate(((first, JOB), (second, "studio-" + "d" * 64))):
        assert (
            guard(tmp_path, api, p, job)(BASE + ":generateContent", payload(), {})
            == responses[index]
        )
    assert api.generated == 2 and len(api.calls) == requests
    with sqlite3.connect(private_billing_path(tmp_path)) as db:
        assert db.execute(
            "SELECT policy_id,reservation_microusd FROM calls ORDER BY policy_id"
        ).fetchall() == [
            (first.authorization_sha256, first.reservation(10)),
            (second.authorization_sha256, second.reservation(10)),
        ]


@pytest.mark.parametrize("limit", ["rows", "bytes", "deadline"])
def test_studio_billing_whole_journal_limits_preserve_evidence(
    tmp_path: Path, api: LocalProtocol, limit: str
) -> None:
    p = policy()
    guarded = guard(tmp_path, api, p)
    guard(tmp_path, api, replace(p, authorization_sha256="c" * 64), "studio-" + "d" * 64)
    before = _billing_bytes(guarded.path)
    with (
        sqlite3.connect(guarded.path) as db,
        pytest.raises(StudioStorageError, match="limit|budget"),
    ):
        if limit == "rows":
            guarded._inspect(db, max_rows=1)
        elif limit == "bytes":
            guarded._inspect(db, max_bytes=1)
        else:
            guarded._inspect(db, max_seconds=1e-9)
    assert api.calls == [] and _billing_bytes(guarded.path) == before
