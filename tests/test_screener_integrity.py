"""Real codec/factory boundaries; supplied protocol bodies are not model quality evidence."""

from __future__ import annotations

import json
import math
import threading
import urllib.request
from contextlib import suppress
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from hawedit.clip import DiscoveryPath
from hawedit.discovery import MergedCandidate
from hawedit.pipeline import build_and_run, build_parser
from hawedit.screener import GeminiFlashScreener, JevScreener, ScreenedCandidate, get_screener


def candidate(cid: str = "candidate-1") -> MergedCandidate:
    return MergedCandidate(cid, "episode", 100, 1000, DiscoveryPath.VERBAL, (cid,))


def row() -> dict[str, Any]:
    return dict(
        candidate_id="candidate-1",
        hook_score=0.8,
        payoff_score=0.7,
        is_self_contained=True,
        misleading_risk=0.1,
    )


def flash_body(rows: object) -> bytes:
    return json.dumps(
        {"candidates": [{"content": {"parts": [{"text": json.dumps({"candidates": rows})}]}}]}
    ).encode()


def legacy_body() -> dict[str, Any]:
    return {
        "questions": {
            "is_self_contained": {"answer": True},
            "hook_score": {"answer": 88.0},
            "payoff_score": {"answer": 75.0},
            "misleading_risk": {"probability": 0.05},
        }
    }


@pytest.mark.parametrize("kind", ["gemini-flash", "jev"])
def test_screener_factory_routes_explicit_transport(kind: str) -> None:
    calls: list[urllib.request.Request] = []
    body = flash_body([row()]) if kind == "gemini-flash" else json.dumps(legacy_body()).encode()

    def transport(request: urllib.request.Request) -> bytes:
        calls.append(request)
        return body

    selected = get_screener(
        kind, gemini_key="diagnostic-key", typesafe_key="diagnostic-key", transport=transport
    )
    assert selected is not None
    result = selected.screen([(candidate(), "diagnostic transcript")])
    assert len(calls) == 1 and len(result) == 1
    assert result[0].candidate_id == "candidate-1"
    assert calls[0].method == "POST"


@pytest.mark.parametrize("kind", ["gemini-flash", "jev"])
def test_explicit_false_valued_screener_transport_never_falls_back(kind: str) -> None:
    body = flash_body([row()]) if kind == "gemini-flash" else json.dumps(legacy_body()).encode()

    class FalseValuedTransport:
        def __init__(self) -> None:
            self.calls: list[urllib.request.Request] = []

        def __bool__(self) -> bool:
            return False

        def __call__(self, request: urllib.request.Request) -> bytes:
            self.calls.append(request)
            return body

    transport = FalseValuedTransport()
    selected = get_screener(
        kind, gemini_key="diagnostic-key", typesafe_key="diagnostic-key", transport=transport
    )
    assert isinstance(selected, GeminiFlashScreener | JevScreener)
    assert selected._transport is transport
    result = selected.screen([(candidate(), "diagnostic transcript")])
    assert len(transport.calls) == 1 and len(result) == 1
    assert result[0].candidate_id == "candidate-1"
    assert transport.calls[0].method == "POST"


@pytest.mark.parametrize("kind", ["gemini-flash", "jev"])
def test_shared_builder_refuses_unguarded_screening_before_inputs(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    def forbidden_credentials(_key: str) -> str:
        raise AssertionError("Credential work occurred before guarded screening refusal")

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr("hawedit.credentials.read_credential", forbidden_credentials)
    args = build_parser().parse_args(
        [
            "absent-source.mp4",
            "--omni-asr",
            "--gemini",
            "--auto-select",
            "--screener",
            kind,
        ]
    )
    calls: list[str] = []

    def judged(url: str, payload: bytes | None, headers: object) -> tuple[int, str]:
        calls.append(url)
        raise AssertionError("Paid transport was reached")

    with pytest.raises(ValueError, match="screener transport"):
        build_and_run(args, judge_transport=judged)
    assert calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("hook_score", None),
        ("hook_score", True),
        ("hook_score", "0.8"),
        ("hook_score", math.nan),
        ("payoff_score", math.inf),
        ("payoff_score", -0.1),
        ("misleading_risk", 2),
        ("misleading_risk", False),
        ("is_self_contained", "false"),
        ("is_self_contained", 1),
    ],
)
def test_flash_refuses_unmeasured_or_coerced_scores(field: str, value: object) -> None:
    damaged = row()
    damaged[field] = value
    backend = GeminiFlashScreener(
        api_key="diagnostic-key", transport=lambda req: flash_body([damaged])
    )
    with pytest.raises(ValueError):
        backend.screen([(candidate(), "diagnostic transcript")])


@pytest.mark.parametrize(
    "field", ["hook_score", "payoff_score", "misleading_risk", "is_self_contained"]
)
def test_flash_refuses_missing_score_fields(field: str) -> None:
    damaged = row()
    del damaged[field]
    backend = GeminiFlashScreener(
        api_key="diagnostic-key", transport=lambda req: flash_body([damaged])
    )
    with pytest.raises(ValueError):
        backend.screen([(candidate(), "diagnostic transcript")])


@pytest.mark.parametrize("damage", ["foreign", "duplicate", "omitted", "empty"])
def test_flash_refuses_foreign_duplicate_or_incomplete_batch(damage: str) -> None:
    rows = [row()]
    inputs = [(candidate(), "diagnostic transcript")]
    if damage == "foreign":
        rows[0]["candidate_id"] = "unrequested"
    elif damage == "duplicate":
        rows.append(row())
    elif damage == "omitted":
        inputs.append((candidate("candidate-2"), "other transcript"))
    else:
        rows = []
    backend = GeminiFlashScreener(api_key="diagnostic-key", transport=lambda req: flash_body(rows))
    with pytest.raises(ValueError):
        backend.screen(inputs)


@pytest.mark.parametrize("kind", ["gemini-flash", "jev"])
@pytest.mark.parametrize("damage", ["duplicate-id", "empty-text", "boolean-top-k"])
def test_screeners_refuse_invalid_input_before_egress(kind: str, damage: str) -> None:
    calls: list[urllib.request.Request] = []

    def transport(request: urllib.request.Request) -> bytes:
        calls.append(request)
        raise AssertionError("Invalid input reached egress")

    backend = (GeminiFlashScreener if kind == "gemini-flash" else JevScreener)(
        api_key="diagnostic-key", transport=transport
    )
    inputs = [(candidate(), "diagnostic transcript")]
    top_k = 1
    if damage == "duplicate-id":
        inputs *= 2
    elif damage == "empty-text":
        inputs = [(candidate(), " ")]
    else:
        top_k = True
    with pytest.raises(ValueError):
        backend.screen(inputs, top_k=top_k)
    assert calls == []


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "string-boolean",
        "string-number",
        "boolean-score",
        "negative",
        "excess",
        "nan",
        "current-wire",
    ],
)
def test_jev_refuses_unmeasured_legacy_or_mismatched_wire(damage: str) -> None:
    data = legacy_body()
    q = data["questions"]
    if damage == "missing":
        del q["misleading_risk"]
    elif damage == "string-boolean":
        q["is_self_contained"]["answer"] = "false"
    elif damage == "string-number":
        q["hook_score"]["answer"] = "88"
    elif damage == "boolean-score":
        q["hook_score"]["answer"] = True
    elif damage == "negative":
        q["hook_score"]["answer"] = -1
    elif damage == "excess":
        q["misleading_risk"]["probability"] = 10
    elif damage == "nan":
        q["payoff_score"]["answer"] = math.nan
    else:
        data = {
            "model": "jev-1.13.0",
            "answers": {"is_self_contained": {"type": "noul", "noul": 0.9}},
        }
    backend = JevScreener(api_key="diagnostic-key", transport=lambda req: json.dumps(data).encode())
    with pytest.raises(ValueError):
        backend.screen_one("candidate-1", "diagnostic transcript")


@pytest.mark.parametrize("kind", ["gemini-flash", "jev"])
@pytest.mark.parametrize("damage", ["duplicate-json", "oversized"])
def test_screeners_refuse_ambiguous_or_unbounded_json(kind: str, damage: str) -> None:
    valid = flash_body([row()]) if kind == "gemini-flash" else json.dumps(legacy_body()).encode()
    if damage == "duplicate-json":
        name = "candidates" if kind == "gemini-flash" else "questions"
        body = b'{"' + name.encode() + b'":null,' + valid[1:]
    else:
        body = valid + b" " * (2 * 1024**2)
    backend = (GeminiFlashScreener if kind == "gemini-flash" else JevScreener)(
        api_key="diagnostic-key", transport=lambda req: body
    )
    with pytest.raises(ValueError):
        backend.screen([(candidate(), "diagnostic transcript")])


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate_id", ""),
        ("screener", ""),
        ("is_self_contained", "false"),
        ("hook_score", True),
        ("payoff_score", False),
        ("misleading_risk", True),
        ("composite_score", False),
    ],
)
def test_screened_candidate_refuses_coerced_record_fields(field: str, value: object) -> None:
    valid = ScreenedCandidate("candidate-1", 0.8, 0.7, True, 0.1, 0.78, "diagnostic")
    damaged: dict[str, Any] = {field: value}
    with pytest.raises(ValueError):
        replace(valid, **damaged)


@pytest.mark.parametrize("kind", ["gemini-flash", "jev"])
def test_default_screener_http_reads_have_actual_response_bound(kind: str) -> None:
    body = b" " * (2 * 1024**2 + 10)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            with suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/bounded")
        backend = GeminiFlashScreener if kind == "gemini-flash" else JevScreener
        with pytest.raises(ValueError, match="bound"):
            backend._default_transport(request)
    finally:
        server.shutdown()
        thread.join(5)
        server.server_close()
    assert not thread.is_alive()


def test_flash_preserves_zero_false_and_multipart_completion() -> None:
    measured = row()
    measured.update(hook_score=0, payoff_score=0, is_self_contained=False, misleading_risk=1)
    text = json.dumps({"candidates": [measured]})
    body = json.dumps(
        {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {"thought": True, "text": "not a measurement"},
                            {"text": text[:30]},
                            {"text": text[30:]},
                        ]
                    },
                }
            ]
        }
    ).encode()
    backend = GeminiFlashScreener(api_key="diagnostic-key", transport=lambda req: body)
    result = backend.screen([(candidate(), "diagnostic transcript")])
    assert result[0].hook_score == result[0].payoff_score == result[0].composite_score == 0
    assert result[0].is_self_contained is False
    assert result[0].misleading_risk == 1
    assert result[0].raw == measured


@pytest.mark.parametrize("reason", ["MAX_TOKENS", "SAFETY", None])
def test_flash_refuses_incomplete_finish_reason(reason: object) -> None:
    envelope = json.loads(flash_body([row()]))
    envelope["candidates"][0]["finishReason"] = reason
    backend = GeminiFlashScreener(
        api_key="diagnostic-key", transport=lambda req: json.dumps(envelope).encode()
    )
    with pytest.raises(ValueError, match="incomplete"):
        backend.screen([(candidate(), "diagnostic transcript")])


def test_flash_validates_rows_below_top_k() -> None:
    damaged = row()
    damaged.update(candidate_id="candidate-2", hook_score=None)
    backend = GeminiFlashScreener(
        api_key="diagnostic-key", transport=lambda req: flash_body([row(), damaged])
    )
    with pytest.raises(ValueError):
        backend.screen(
            [(candidate(), "first transcript"), (candidate("candidate-2"), "second transcript")],
            top_k=1,
        )


def test_flash_refuses_duplicate_inner_json_keys() -> None:
    text = '{"candidates":[],"candidates":' + json.dumps([row()]) + "}"
    body = json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode()
    backend = GeminiFlashScreener(api_key="diagnostic-key", transport=lambda req: body)
    with pytest.raises(ValueError, match="repeats"):
        backend.screen([(candidate(), "diagnostic transcript")])


def test_shared_builder_routes_screening_through_explicit_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.pipeline import StageSkipped
    from test_gemini import verdict_fields
    from test_pipeline import FIXTURE, a_transcript
    from test_studio_billing import KEY, LocalProtocol, guard

    transcript = tmp_path / "transcript.json"
    transcript.write_text(a_transcript(FIXTURE.stem).to_json(), encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    judging = LocalProtocol()
    screening = LocalProtocol()
    routes: list[str] = []

    def judge_response(document: dict[str, Any]) -> str:
        fields = verdict_fields(payoff_at_ms=1000)
        if "candidates" in document["generationConfig"]["responseSchema"]["properties"]:
            fields = {
                "candidates": [
                    {"in_ms": 100, "out_ms": 4100, "score": 0.9, "reason_ckb": fields["reason_ckb"]}
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

    def screen_response(document: dict[str, Any]) -> str:
        prompt = document["contents"][0]["parts"][0]["text"]
        inputs = json.loads(prompt.split("Input candidates:\n", 1)[1])
        assert inputs and all(item["transcript_ckb"] for item in inputs)
        rows = [dict(row(), candidate_id=item["candidate_id"]) for item in inputs]
        return flash_body(rows).decode()

    def screen_transport(request: urllib.request.Request) -> bytes:
        routes.append(request.full_url)
        assert isinstance(request.data, bytes)
        status, response = screening.transport(
            request.full_url.split("?", 1)[0], request.data, request.headers
        )
        assert status == 200
        return response.encode()

    judging.response = judge_response
    screening.response = screen_response
    try:
        args = build_parser().parse_args(
            [
                str(FIXTURE),
                "--transcript",
                str(transcript),
                "--gemini",
                "--auto-select",
                "--screener",
                "gemini-flash",
                "--min-clip-seconds",
                "1.5",
                "--work-dir",
                str(tmp_path / "work"),
            ]
        )
        result = build_and_run(
            args, judge_transport=guard(tmp_path, judging), screener_transport=screen_transport
        )
        assert result.candidates, result.discovery
        assert len(routes) == screening.generated == 1
        assert "/models/gemini-2.5-flash-lite:generateContent" in routes[0]
        assert judging.generated == 6
        assert result.clip is not None and result.clip.editorial is not None
        assert isinstance(result.delivery, StageSkipped)
    finally:
        screening.close()
        judging.close()
