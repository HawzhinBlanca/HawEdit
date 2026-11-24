"""Resolved token budgets and tokenizer revisions are not credentials."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

import test_candidate_review as review_fixtures
from hawedit.candidate_review import CandidateReviewError
from test_candidate_review import ReviewCase

case = review_fixtures.case
tools = review_fixtures.tools


@pytest.mark.parametrize(
    ("field", "value"),
    [("max_output_tokens", 16384), ("max_input_tokens", 200000), ("tokenizer_revision", "c" * 64)],
)
def test_review_configuration_accepts_noncredential_token_limits(
    case: ReviewCase, field: str, value: object
) -> None:
    context = replace(case, configuration={**case.configuration, field: value})
    context.prepare()
    context.sign()
    context.verify()
    envelope = json.loads((context.packet / "review.json").read_bytes())
    assert envelope["producer"]["effective_configuration"][field] == value


@pytest.mark.parametrize(
    "field",
    [
        "api_key",
        "apiKey",
        "access_token",
        "refreshToken",
        "hf_token_path",
        "client_token",
        "authorization",
    ],
)
def test_review_configuration_still_refuses_credential_fields(case: ReviewCase, field: str) -> None:
    context = replace(case, configuration={**case.configuration, field: "not-a-real-credential"})
    with pytest.raises(CandidateReviewError, match="must not contain credentials"):
        context.prepare()
    assert not context.packet.exists()
