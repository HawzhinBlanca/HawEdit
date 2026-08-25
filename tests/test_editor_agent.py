"""The editor agent: it can propose, and structurally it cannot commit.

`editor_agent.py`'s whole reason to exist separately from `agent.py` is a narrower promise than
even a read-only one: it can check whether a boundary or caption revision would be legal, and
nothing about it can approve or write one. Two things are checked here, not just the ordinary
"the tool works" coverage `test_proposals.py` already gives the propose functions themselves:

- The agent's registered tool set has exactly the two propose tools, and neither is named
  anything that suggests commit/approve/apply.
- `commit_boundary_revision`/`commit_caption_revision` do not appear anywhere reachable from
  this module's own source — an AST-level guarantee, the same kind `test_agent.py` holds
  `agent.py` to, rather than a promise the docstring makes and nothing checks.
"""

from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

import pytest

pytest.importorskip("pydantic_ai")

from hawedit.agent import Deps
from hawedit.boundary import Boundary
from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Output
from hawedit.editor_agent import build_editor_agent
from hawedit.proposals import BoundaryRevisionProposal, CaptionRevisionProposal
from hawedit.sentences import Sentence
from hawedit.transcripts import AsrProvenance, Word

ROOT = Path(__file__).resolve().parents[1]
EDITOR_AGENT_SRC = ROOT / "src" / "hawedit" / "editor_agent.py"

_DEFAULT_BOUNDARY: dict[str, object] = {
    "anchor_in_ms": 100,
    "anchor_out_ms": 4100,
    "final_in_ms": 0,
    "final_out_ms": 4300,
    "in_extended_by": "vad_onset",
    "out_extended_by": "tail",
    "sentence_complete": True,
    "confidence": None,
}

_WORDS = (
    Word(w="ڕۆژنامەوانی", start_ms=0, end_ms=800, conf=0.95),
    Word(w="کوردی.", start_ms=800, end_ms=1_700, conf=0.94),
)


def _clip_dict(caption_style: str = "line") -> dict[str, object]:
    """A minimal but real `Clip.to_dict()` — needed because `TestModel` calls every registered
    tool, including `propose_caption_revision_tool`, which reads `clip.output.caption_style`."""
    boundary = Boundary(
        anchor_in_ms=100,
        anchor_out_ms=4100,
        final_in_ms=0,
        final_out_ms=4300,
        in_extended_by="vad_onset",
        out_extended_by="tail",
        sentence_complete=True,
        confidence=None,
    )
    clip = Clip(
        clip_id="fixture-0",
        media_id="fixture",
        media_sha256="a" * 64,
        in_ms=boundary.final_in_ms,
        out_ms=boundary.final_out_ms,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=boundary,
        transcript=ClipTranscript(
            raw_ckb="ڕۆژنامەوانی کوردی.",
            norm_ckb="ڕۆژنامەوانی کوردی.",
            en_aux=None,
            words=_WORDS,
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        ),
        output=Output(
            title_ckb="t",
            description_ckb="d",
            crop_target="9:16",
            caption_style=caption_style,
            durations=(30,),
        ),
    )
    return clip.to_dict()


def _write_report(work_dir: Path) -> None:
    report: dict[str, object] = {
        "media_id": "fixture",
        "source": "x.mp4",
        "work_dir": str(work_dir),
        "complete": True,
        "skipped": [],
        "boundary": _DEFAULT_BOUNDARY,
        "candidates": [],
        "rejected": [],
        "clip": _clip_dict(),
        "render": None,
        "delivery": None,
        "selected_sentences": [dataclasses.asdict(Sentence(words=_WORDS, complete=True))],
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")


def test_editor_agent_module_never_calls_commit(tmp_path: Path) -> None:
    """`commit_boundary_revision`/`commit_caption_revision` must not be referenced anywhere in
    this module's source — not imported, not called, not passed around. If a future edit adds a
    commit-capable tool here, this fails on the `ast.Name`/`ast.Attribute` reference itself, not
    on behavior a test would have to think to exercise."""
    tree = ast.parse(EDITOR_AGENT_SRC.read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert "commit_boundary_revision" not in names
    assert "commit_caption_revision" not in names


def test_the_editor_agent_has_exactly_two_tools_and_they_only_propose(tmp_path: Path) -> None:
    """Same pinned-version rationale as `agent.py`'s equivalent test (`pyproject.toml` pins
    `pydantic-ai-slim==2.28.0` exactly)."""
    from pydantic_ai.models.test import TestModel

    _write_report(tmp_path)
    agent = build_editor_agent(TestModel(), Deps(work_dir=tmp_path))
    tool_names = {tool.name for tool in agent._function_toolset.tools.values()}
    assert tool_names == {"propose_boundary_revision_tool", "propose_caption_revision_tool"}


def test_the_agent_reports_an_invalid_proposal_rather_than_silently_fixing_it(
    tmp_path: Path,
) -> None:
    from pydantic_ai.models.test import TestModel

    _write_report(tmp_path)
    # TestModel's default arg generation for an int parameter is 0 for both — final_out_ms=0
    # is before anchor_out_ms=4100, an invalid proposal. This is the case worth asserting on:
    # the agent must surface that as an invalid result, not silently clamp or retry with a
    # different number the model was never asked to pick.
    agent = build_editor_agent(TestModel(), Deps(work_dir=tmp_path))
    result = agent.run_sync("propose a revision", deps=Deps(work_dir=tmp_path))
    assert '"valid":false' in result.output.replace(" ", "")


def test_the_proposal_tool_returns_the_typed_dataclass_not_a_bare_string(tmp_path: Path) -> None:
    """`propose_boundary_revision` itself already returns `BoundaryRevisionProposal` — this
    confirms the wrapped tool doesn't lose that on the way through pydantic-ai's call layer by
    checking the same fields survive round-trip in the final agent output."""
    from pydantic_ai.models.test import TestModel

    _write_report(tmp_path)
    agent = build_editor_agent(TestModel(), Deps(work_dir=tmp_path))
    result = agent.run_sync("propose a revision", deps=Deps(work_dir=tmp_path))
    assert "media_id" in result.output
    assert "anchor_in_ms" in result.output


def test_direct_call_still_returns_the_real_dataclass_type(tmp_path: Path) -> None:
    from hawedit.proposals import propose_boundary_revision

    _write_report(tmp_path)
    proposal = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=4500)
    assert isinstance(proposal, BoundaryRevisionProposal)


def test_the_caption_tool_reports_a_valid_proposal(tmp_path: Path) -> None:
    """`TestModel`'s default arg for `Literal["line", "word_highlight"]` is `"line"` (checked
    directly against the real schema before relying on it) — the same as `_clip_dict`'s own
    original style, so this exercises the *valid* path, unlike the boundary tool's default
    invalid case above. Both are worth having: a gate that only ever sees failures would not
    catch one that always reports valid regardless of the real check."""
    from pydantic_ai.models.test import TestModel

    _write_report(tmp_path)
    agent = build_editor_agent(TestModel(), Deps(work_dir=tmp_path))
    result = agent.run_sync("propose a caption revision", deps=Deps(work_dir=tmp_path))
    assert '"valid":true' in result.output.replace(" ", "")
    assert "proposed_caption_style" in result.output


def test_direct_caption_call_still_returns_the_real_dataclass_type(tmp_path: Path) -> None:
    from hawedit.proposals import propose_caption_revision

    _write_report(tmp_path)
    proposal = propose_caption_revision(tmp_path, "word_highlight")
    assert isinstance(proposal, CaptionRevisionProposal)
