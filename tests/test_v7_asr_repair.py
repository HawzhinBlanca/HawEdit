"""Tests for Item #5 (D-381): Sorani ASR orthography repair & LocalLlmJsonClient."""

from __future__ import annotations

import http.server
import json
import socket
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import pytest

from hawedit.caption_polish import (
    CAPTION_POLISH_SCHEMA,
    DEFAULT_LOCAL_LLM_URL,
    KURDISH_ASR_BIGRAM_FIXES,
    KURDISH_ASR_ORTHOGRAPHY_FIXES,
    LOCAL_LLM_MODEL_ENV,
    LOCAL_LLM_URL_ENV,
    LocalLlmJsonClient,
    LocalLlmUnavailable,
    polish_clip_sentences,
    repair_kurdish_asr_orthography,
)
from hawedit.judge import StructuredJsonClient
from hawedit.sentences import Sentence, assert_deliverable_order
from hawedit.transcripts import Word

# Real AI s86-87 word sequence from V6 canonical transcript (`zar-ai-half-episode-lamo`, s86-87).
_AI_S86_WORDS: tuple[str, ...] = (
    "ئێستا",
    "بۆچی",
    "ئەگەزانی",
    "لەم",
    "ماوەی",
    "ئەنترۆپیک",
    "ما",
    "ئێ",
    "فەیبوو",
    "فایف",
    "ئەوە",
    "مۆدەی",
    "بڵاو",
    "کردەوە",
    "بۆ",
    "بەیانیەکەی",
    "یەکسەر",
    "خمەم",
    "نوعیان",
    "کە",
    "لە",
    "عالەمانەیان",
    "توانی",
    "ئا",
    "چونکە",
    "کەسێک",
    "توانی",
    "ڕیستیک",
    "یەعنی",
    "ڕێگریەکانی",
    "لێ",
    "لابا",
    "لیمیتەکەی",
    "لێ",
    "لابا",
    "ئێستا",
    "هەنێ",
    "مۆدێڵ",
    "بڵاو",
    "بنەوە",
    "کە",
    "لە",
    "ئەتوانی",
    "لە",
    "کۆمپیوتەرەکەی",
    "خۆتەوە",
    "بە",
    "لۆکەڵ",
    "ئیشی",
    "پێبکەی",
    "یەعنی",
    "زانیاریەکان",
    "ناچێتە",
    "دەرەوە",
    "لەناو",
    "کۆمپیوتەرەکەی",
    "خۆت",
    "حسابی",
    "ئەکا",
)

_AI_S87_WORDS: tuple[str, ...] = (
    "ڕێگەیان",
    "دۆزیوەتەوە",
    "بۆ",
    "ئەوەی",
    "ئەم",
    "لیمیتیانە",
    "لابەن",
    "ئەم",
    "ڕێگریانە",
    "لابەن",
    "لەسەری",
    "ئیتر",
    "قانوون",
    "لەدانن",
    "ئەی",
    "ئاینە",
    "چێتە",
    "دەر",
    "ئەگەر",
    "بچێتە",
    "دەر",
    "نازانی",
    "تۆ",
    "چی",
    "ئەکا",
    "بۆیە",
    "زۆر",
    "زۆر",
    "خەڵک",
    "لەوە",
    "ئەترسێ",
    "لە",
    "ئێ",
    "ئای",
)

# Real Cooking s7-7 word sequence from V6 canonical transcript (`cooking-v6`, s7).
_COOKING_S7_WORDS: tuple[str, ...] = (
    "پێش",
    "ئەوەی",
    "کە",
    "بچینە",
    "دەرەوە",
    "پێش",
    "ئەوەی",
    "نانەکە",
    "بخۆین",
    "پێش",
    "ئەوەی",
    "بچینە",
    "ڕەستۆرانتەکە",
    "من",
    "بەو",
    "کەسە",
    "ئەڵێم",
    "زۆر",
    "زۆر",
    "حەز",
    "ئەکەم",
    "دەعوەتی",
    "من",
    "بیت",
    "دوای",
    "نانەکەمان",
    "خوار",
    "بە",
    "شەڕ",
    "لەبەردەم",
    "کاشەرەکە",
    "و",
    "نازانم",
    "چی",
    "و",
    "چی",
    "بزانە",
    "چاوەڕێی",
    "چیەکە",
    "هەشتێکی",
    "ویست",
    "داوای",
    "کاتەوە",
    "وەردەری",
    "کا",
    "ئەو",
    "کاتە",
    "تووشی",
    "ئەو",
    "کێشەیەش",
    "نابین",
)


def _make_sentence(
    tokens: tuple[str, ...],
    *,
    start_ms: int = 1000,
    step_ms: int = 300,
    complete: bool = True,
) -> Sentence:
    words = tuple(
        Word(
            w=tok,
            start_ms=start_ms + idx * step_ms,
            end_ms=start_ms + idx * step_ms + 240,
            conf=0.91,
        )
        for idx, tok in enumerate(tokens)
    )
    return Sentence(words=words, complete=complete)


class _RecordingJsonClient:
    """Minimal `StructuredJsonClient` test double capturing prompts and schemas."""

    model_id = "local-test-model"

    def __init__(self, response_json: str) -> None:
        self._response_json = response_json
        self.seen_parts: list[list[dict[str, Any]]] = []
        self.seen_schemas: list[Mapping[str, Any]] = []

    def count_parts(self, parts: list[dict[str, Any]]) -> int:
        return sum(len(str(p.get("text", ""))) for p in parts)

    def generate_json(self, parts: list[dict[str, Any]], schema: Mapping[str, Any]) -> str:
        self.seen_parts.append(parts)
        self.seen_schemas.append(schema)
        return self._response_json


@contextmanager
def _local_llm_server(
    *,
    models_payload: object = None,
    chat_payload: object = None,
    chat_status: int = 200,
    models_status: int = 200,
    chat_delay_s: float = 0.0,
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Spin up a real loopback HTTP server simulating an OpenAI-compatible LM Studio API."""
    recorded: list[dict[str, Any]] = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            recorded.append(
                {
                    "method": "GET",
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                }
            )
            body = json.dumps(models_payload).encode("utf-8")
            self.send_response(models_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8")
            recorded.append(
                {
                    "method": "POST",
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                    "body": json.loads(raw_body) if raw_body else None,
                }
            )
            if chat_delay_s > 0:
                time.sleep(chat_delay_s)
            if isinstance(chat_payload, str):
                body = chat_payload.encode("utf-8")
            else:
                body = json.dumps(chat_payload, ensure_ascii=False).encode("utf-8")
            self.send_response(chat_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/v1", recorded
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_repair_kurdish_asr_orthography_real_ai_s86_87() -> None:
    """D-381: Deterministic ASR repair fixes real AI s86-87 errors with 1:1 timestamp lock."""
    s86 = _make_sentence(_AI_S86_WORDS, start_ms=1000)
    s87 = _make_sentence(_AI_S87_WORDS, start_ms=25_000)
    originals = (s86, s87)
    orig_snapshot = [[(w.w, w.start_ms, w.end_ms, w.conf) for w in s.words] for s in originals]

    result = polish_clip_sentences(originals, client=None)

    assert result.applied is True
    assert result.rejected_reason is None
    assert result.stutters_removed == 0
    # s86 fixes (6): ئەگەزانی, مۆدەی(بڵاو), بەیانیەکەی, ڕیستیک, ڕێگریەکانی, زانیاریەکان
    # s87 fixes (4): ڕێگریانە, ئاینە+چێتە (2 words), ئێ(ئای)
    assert result.words_polished == 10

    repaired_s86 = [w.w for w in result.sentences[0].words]
    repaired_s87 = [w.w for w in result.sentences[1].words]

    assert repaired_s86[2] == "ئەزانی"
    assert repaired_s86[11] == "مۆدێل"
    assert repaired_s86[12] == "بڵاو"
    assert repaired_s86[15] == "بەیانییەکەی"
    assert repaired_s86[27] == "ڕیستریکت"
    assert repaired_s86[29] == "ڕێگرییەکانی"
    assert repaired_s86[51] == "زانیارییەکان"

    # Zero false positives on consonant-stem nouns and non-target `ئێ` before `فەیبوو`.
    assert repaired_s86[7] == "ئێ"
    assert repaired_s86[44] == "کۆمپیوتەرەکەی"
    assert repaired_s86[55] == "کۆمپیوتەرەکەی"
    assert repaired_s86[5] == "ئەنترۆپیک"

    # s87 repairs & zero false positives.
    assert repaired_s87[8] == "ڕێگرییانە"
    assert repaired_s87[15:17] == ["ئای", "نەچێتە"]
    assert repaired_s87[32:34] == ["ئەی", "ئای"]
    assert repaired_s87[26:28] == ["زۆر", "زۆر"]  # emphatic repeat preserved

    # Strict 1:1 word count, exact CTC timestamps/conf, immutability, and idempotence.
    assert_deliverable_order(result.sentences)
    for orig_s, rep_s in zip(originals, result.sentences, strict=True):
        assert rep_s.complete is orig_s.complete
        assert len(rep_s.words) == len(orig_s.words)
        for orig_w, rep_w in zip(orig_s.words, rep_s.words, strict=True):
            assert rep_w.start_ms == orig_w.start_ms
            assert rep_w.end_ms == orig_w.end_ms
            assert rep_w.conf == orig_w.conf
    assert [[(w.w, w.start_ms, w.end_ms, w.conf) for w in s.words] for s in originals] == (
        orig_snapshot
    )

    second_pass, second_count = repair_kurdish_asr_orthography(result.sentences)
    assert second_count == 0
    assert second_pass == result.sentences


def test_repair_kurdish_asr_orthography_real_cooking_s7() -> None:
    """D-381: Deterministic ASR repair fixes real Cooking s7-7 errors with zero false positives."""
    s7 = _make_sentence(_COOKING_S7_WORDS, start_ms=500)
    result = polish_clip_sentences((s7,), client=None)

    assert result.applied is True
    assert result.rejected_reason is None
    assert result.stutters_removed == 0
    # Cooking s7 fixes (3): ڕەستۆرانتەکە, کاشەرەکە, وەردەری(کا) -> ئۆردەری
    assert result.words_polished == 3

    words = [w.w for w in result.sentences[0].words]
    assert words[12] == "ڕێستۆرانتەکە"
    assert words[30] == "کاشێرەکە"
    assert words[43:45] == ["ئۆردەری", "کا"]

    # Zero false positives on short `چیەکە`, consonant-stem `نانەکە`, and `کێشەیەش`.
    assert words[7] == "نانەکە"
    assert words[17:19] == ["زۆر", "زۆر"]
    assert words[38] == "چیەکە"
    assert words[49] == "کێشەیەش"

    assert len(result.sentences[0].words) == len(s7.words)
    for before, after in zip(s7.words, result.sentences[0].words, strict=True):
        assert after.start_ms == before.start_ms
        assert after.end_ms == before.end_ms
        assert after.conf == before.conf

    second_pass, second_count = repair_kurdish_asr_orthography(result.sentences)
    assert second_count == 0
    assert second_pass == result.sentences


def test_double_yaa_rule_punctuation_and_bigram_guards() -> None:
    """D-381: General Sorani double-yaa rule & bigram guards avoid all false positives."""
    assert KURDISH_ASR_ORTHOGRAPHY_FIXES["ئەزولێن"] == "ئەجووڵێن"
    assert KURDISH_ASR_BIGRAM_FIXES[("مۆدەی", "بڵاو")] == ("مۆدێل", "بڵاو")

    s_pos = _make_sentence(
        (
            "«ڕەستۆرانتەکە»؟",
            "کاشەرەکە.",
            "ئەزولێن",
            "کوردیەکەیان",
            "داواکاریەکان،",
            "یاریەکە",
            "پەیوەندیەکەم",
            "ئەلیکترۆنیەکان",
            "هەرمی",
            "کوردستان",
        ),
        start_ms=100,
    )
    repaired, count = repair_kurdish_asr_orthography((s_pos,))
    assert count == 9
    assert [w.w for w in repaired[0].words] == [
        "«ڕێستۆرانتەکە»؟",
        "کاشێرەکە.",
        "ئەجووڵێن",
        "کوردییەکەیان",
        "داواکارییەکان،",
        "یارییەکە",
        "پەیوەندییەکەم",
        "ئەلیکترۆنییەکان",
        "هەرێمی",
        "کوردستان",
    ]

    # False-positive & boundary guards: vowel-stem glides, consonant stems, already-correct
    # double-yaa, and bigram blocked by non-matching neighbor or terminal punctuation.
    s_guard = _make_sentence(
        (
            "کۆمپیوتەرەکەی",
            "هاوڕێیەکە",
            "کێشەیەکە",
            "ماوەیەکە",
            "بەهرەیەکە",
            "ڤیدۆیەکە",
            "ئایەکە",
            "ئایەکان",
            "چیەکە",
            "بەیانییەکەی",
            "مۆدەی",
            "نوێ",
            "مۆدەی.",
            "بڵاو",
            "ئێ",
            "بەڵام",
        ),
        start_ms=5000,
    )
    unchanged, unchanged_count = repair_kurdish_asr_orthography((s_guard,))
    assert unchanged_count == 0
    assert unchanged[0] == s_guard


def test_polish_prompt_loanword_guidance_and_combined_counts() -> None:
    """D-381: LLM prompt targets English loanword garbles and preserves deterministic fixes."""
    s = _make_sentence(
        ("ئەگەزانی", "ئەنترۆپیک", "فەیبوو", "فایف", "بڵاو", "کردەوە", "بۆ", "بەیانیەکەی"),
        start_ms=0,
    )
    client = _RecordingJsonClient(json.dumps({"replacements": [{"index": 2, "w": "فۆر"}]}))
    res = polish_clip_sentences((s,), client=client)

    assert res.applied is True
    assert res.rejected_reason is None
    # 2 deterministic (ئەگەزانی, بەیانیەکەی) + 1 LLM (فەیبوو -> فۆر)
    assert res.words_polished == 3
    assert [w.w for w in res.sentences[0].words] == [
        "ئەزانی",
        "ئەنترۆپیک",
        "فۆر",
        "فایف",
        "بڵاو",
        "کردەوە",
        "بۆ",
        "بەیانییەکەی",
    ]

    assert len(client.seen_parts) == 1
    prompt = client.seen_parts[0][-1]["text"]
    assert "ما فەیبوو فایف" in prompt
    assert "خمەم نوعیان" in prompt
    assert "عالەمانەیان" in prompt
    assert "ڕیستیک" in prompt
    assert "1-to-1" in prompt
    # The prompt saw already-repaired deterministic tokens (`ئەزانی`, `بەیانییەکەی`).
    assert "0 (0.00-0.24s): ئەزانی" in prompt
    assert "7 (2.10-2.34s): بەیانییەکەی" in prompt

    # If the LLM returns invalid JSON, deterministic fixes are preserved and applied=False.
    bad_client = _RecordingJsonClient("not-json")
    bad_res = polish_clip_sentences((s,), client=bad_client)
    assert bad_res.applied is False
    assert bad_res.rejected_reason is not None
    assert bad_res.words_polished == 2
    assert bad_res.sentences[0].words[0].w == "ئەزانی"
    assert bad_res.sentences[0].words[7].w == "بەیانییەکەی"


def test_local_llm_json_client_protocol_env_and_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-381: LocalLlmJsonClient satisfies StructuredJsonClient, honors env, validates args."""
    monkeypatch.delenv(LOCAL_LLM_URL_ENV, raising=False)
    monkeypatch.delenv(LOCAL_LLM_MODEL_ENV, raising=False)

    default_client = LocalLlmJsonClient()
    assert isinstance(default_client, StructuredJsonClient)
    assert default_client.base_url == DEFAULT_LOCAL_LLM_URL
    assert default_client.model_id == ""
    assert default_client.count_parts([{"text": "abcd" * 5}]) == 5
    assert default_client.count_parts([]) == 0

    monkeypatch.setenv(LOCAL_LLM_URL_ENV, "http://127.0.0.1:4321/v1/")
    monkeypatch.setenv(LOCAL_LLM_MODEL_ENV, "qwen3.8-27b-obliterated")
    env_client = LocalLlmJsonClient()
    assert env_client.base_url == "http://127.0.0.1:4321/v1"
    assert env_client.model_id == "qwen3.8-27b-obliterated"

    with pytest.raises(ValueError, match="base_url"):
        LocalLlmJsonClient(base_url="ftp://127.0.0.1:1234/v1")
    with pytest.raises(ValueError, match="base_url"):
        LocalLlmJsonClient(base_url="")
    with pytest.raises(ValueError, match="timeout_s"):
        LocalLlmJsonClient(timeout_s=0.0)
    with pytest.raises(ValueError, match="timeout_s"):
        LocalLlmJsonClient(timeout_s=True)


def test_local_llm_json_client_end_to_end_and_model_autodiscovery() -> None:
    """D-381: LocalLlmJsonClient auto-discovers chat model, strips wrappers, polishes clips."""
    models_resp = {
        "object": "list",
        "data": [
            {"id": "text-embedding-nomic-embed-text-v1.5", "object": "model"},
            {"id": "qwen3.8-27b-obliterated", "object": "model"},
        ],
    }
    chat_resp = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "<think>Checking Kurdish loanword spelling.</think>\n"
                        "```json\n"
                        '{"replacements": [{"index": 2, "w": "کۆدز"}]}\n'
                        "```"
                    ),
                }
            }
        ]
    }

    with _local_llm_server(models_payload=models_resp, chat_payload=chat_resp) as (
        base_url,
        recorded,
    ):
        client = LocalLlmJsonClient(base_url=base_url, timeout_s=5.0, api_key="local-secret")
        assert client.probe_models() == (
            "text-embedding-nomic-embed-text-v1.5",
            "qwen3.8-27b-obliterated",
        )

        sentence = _make_sentence(
            ("ئەمڕۆ", "ئەگەزانی", "سکۆدس", "لە", "هەولێر", "باس", "دەکەین."),
            start_ms=0,
        )
        res = polish_clip_sentences((sentence,), client=client)

        assert res.applied is True
        assert res.rejected_reason is None
        assert res.words_polished == 2  # ئەگەزانی -> ئەزانی + سکۆدس -> کۆدز
        assert [w.w for w in res.sentences[0].words] == [
            "ئەمڕۆ",
            "ئەزانی",
            "کۆدز",
            "لە",
            "هەولێر",
            "باس",
            "دەکەین.",
        ]
        assert client.model_id == "qwen3.8-27b-obliterated"

        post_reqs = [r for r in recorded if r["method"] == "POST"]
        assert len(post_reqs) == 1
        assert post_reqs[0]["path"] == "/v1/chat/completions"
        assert post_reqs[0]["auth"] == "Bearer local-secret"
        req_body = post_reqs[0]["body"]
        assert req_body["model"] == "qwen3.8-27b-obliterated"
        assert req_body["response_format"]["type"] == "json_schema"
        assert req_body["response_format"]["json_schema"]["strict"] is True
        assert req_body["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
        # Original Gemini CAPTION_POLISH_SCHEMA remains untouched (no additionalProperties).
        assert "additionalProperties" not in CAPTION_POLISH_SCHEMA


def test_local_llm_json_client_fails_loud_on_unavailable_timeout_http_and_bad_payloads() -> None:
    """D-381: Zero silent fallback — every transport/HTTP/protocol fault fails loud."""
    # 1. Connection refused on an unbound localhost port.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        closed_port = sock.getsockname()[1]
    closed_client = LocalLlmJsonClient(
        base_url=f"http://127.0.0.1:{closed_port}/v1",
        model="qwen3.8-27b-obliterated",
        timeout_s=1.0,
    )
    with pytest.raises(LocalLlmUnavailable, match="unavailable"):
        closed_client.generate_json([{"text": "hello"}], CAPTION_POLISH_SCHEMA)

    # 2. HTTP 503 error raises LocalLlmUnavailable loudly.
    with _local_llm_server(
        chat_payload={"error": {"message": "model loading"}},
        chat_status=503,
    ) as (base_url, _):
        err_client = LocalLlmJsonClient(
            base_url=base_url,
            model="qwen3.8-27b-obliterated",
            timeout_s=2.0,
        )
        with pytest.raises(LocalLlmUnavailable, match="HTTP 503"):
            err_client.generate_json([{"text": "hello"}], CAPTION_POLISH_SCHEMA)

    # 3. Request timeout raises LocalLlmUnavailable loudly.
    with _local_llm_server(
        chat_payload={"choices": [{"message": {"content": '{"replacements": []}'}}]},
        chat_delay_s=0.5,
    ) as (base_url, _):
        slow_client = LocalLlmJsonClient(
            base_url=base_url,
            model="qwen3.8-27b-obliterated",
            timeout_s=0.1,
        )
        with pytest.raises(LocalLlmUnavailable, match="unavailable"):
            slow_client.generate_json([{"text": "hello"}], CAPTION_POLISH_SCHEMA)

    # 4. Only embedding models loaded -> resolve_model raises LocalLlmUnavailable.
    with _local_llm_server(
        models_payload={"data": [{"id": "text-embedding-nomic-embed-text-v1.5"}]},
    ) as (base_url, _):
        embed_only = LocalLlmJsonClient(base_url=base_url, timeout_s=2.0)
        with pytest.raises(LocalLlmUnavailable, match="No chat model loaded"):
            embed_only.resolve_model()

    # 5. Missing choices or malformed JSON response -> LocalLlmUnavailable.
    with _local_llm_server(chat_payload={"choices": []}) as (base_url, _):
        empty_choices = LocalLlmJsonClient(
            base_url=base_url,
            model="qwen3.8-27b-obliterated",
            timeout_s=2.0,
        )
        with pytest.raises(LocalLlmUnavailable, match="choices"):
            empty_choices.generate_json([{"text": "hello"}], CAPTION_POLISH_SCHEMA)

    with _local_llm_server(chat_payload="<html>bad gateway</html>") as (base_url, _):
        bad_json = LocalLlmJsonClient(
            base_url=base_url,
            model="qwen3.8-27b-obliterated",
            timeout_s=2.0,
        )
        with pytest.raises(LocalLlmUnavailable, match="invalid JSON"):
            bad_json.generate_json([{"text": "hello"}], CAPTION_POLISH_SCHEMA)
