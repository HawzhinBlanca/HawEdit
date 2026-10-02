"""Capture actual definitions and callers before/after the authority guard unit."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("before", "final"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    configuration = importlib.import_module("serena.config.serena_config")
    agent_module = importlib.import_module("serena.agent")
    tools = importlib.import_module("serena.tools")
    config = configuration.SerenaConfig.from_config_file().with_headless_mode_overrides()
    config.language_backend = configuration.LanguageBackend.LSP
    agent = agent_module.SerenaAgent(project=str(root), serena_config=config)
    targets = {
        "src/hawedit/editorial_acceptance.py": (
            "AcceptanceScorecard", "AcceptanceScorecard/to_dict", "compute_acceptance_scorecard",
            "ScopedAcceptanceReport", "ScopedAcceptanceReport/to_dict", "ScopedAcceptanceReport/assert_accepted",
            "evaluate_scoped_acceptance", "SustainedAcceptanceReport", "SustainedAcceptanceReport/to_dict",
            "SustainedAcceptanceReport/assert_sustained", "evaluate_sustained_acceptance",
        ),
        "src/hawedit/visual_scorecard.py": (
            "VisualScorecard", "VisualScorecard/is_release_eligible", "VisualScorecard/evaluate_leadership_claim",
            "VisualScorecard/to_dict",
        ),
        "tests/test_editorial_acceptance.py": (
            "test_acceptance_requires_current_evidence_and_reports_insufficient_sample",
            "test_sustained_acceptance_requires_fresh_holdout_and_use_window",
        ),
        "tests/test_visual_scorecard.py": (
            "test_visual_scorecard_requires_unseen_current_evidence_and_full_accounting",
        ),
    }
    records = []
    try:
        finder = agent.get_tool(tools.FindSymbolTool)
        references = agent.get_tool(tools.FindReferencingSymbolsTool)
        for path, symbols in targets.items():
            for symbol in symbols:
                with finder.symbol_dict_grouper.disabled_context():
                    definition = agent.execute_task(
                        lambda p=path, n=symbol: finder.apply(n, relative_path=p, depth=1)
                    )
                with references.symbol_dict_grouper.disabled_context():
                    callers = agent.execute_task(
                        lambda p=path, n=symbol: references.apply(n, relative_path=p)
                    )
                records.append({"path": path, "symbol": symbol, "definition": definition, "references": callers})
        destination = root / f"specs/evidence-based-studio/serena-T8-authority-{args.phase}-map.json"
        if destination.exists():
            raise RuntimeError("Refusing to overwrite actual authority mapping")
        destination.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        print(f"Captured {len(records)} actual authority guard records", flush=True)
    finally:
        agent.on_shutdown()


if __name__ == "__main__":
    main()
