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
from dataclasses import replace
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
    with sqlite3.connect(private_billing_path(tmp_path)) as db:
        db.execute(
            f"CREATE TRIGGER outage BEFORE {operation} ON calls "
            "BEGIN SELECT RAISE(ABORT, 'actual storage outage'); END"
        )
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
