"""Fresh signed-study and flag-only authority caller mapping; research only."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    configuration = importlib.import_module("serena.config.serena_config")
    agent_module = importlib.import_module("serena.agent")
    tools = importlib.import_module("serena.tools")
    config = configuration.SerenaConfig.from_config_file().with_headless_mode_overrides()
    config.language_backend = configuration.LanguageBackend.LSP
    agent = agent_module.SerenaAgent(project=str(root), serena_config=config)
    targets = [
        "_verify_signature", "_freeze_study_items", "_review_packet",
        "prepare_editorial_study", "evaluate_editorial_study",
        "compute_acceptance_scorecard", "evaluate_scoped_acceptance",
        "ScopedAcceptanceReport/assert_accepted", "evaluate_sustained_acceptance",
        "SustainedAcceptanceReport/assert_sustained",
        "validate_acceptance_split", "partition_episode_disjoint",
    ]
    records = []
    try:
        finder = agent.get_tool(tools.FindSymbolTool)
        references = agent.get_tool(tools.FindReferencingSymbolsTool)
        for name in targets:
            with finder.symbol_dict_grouper.disabled_context():
                definition = agent.execute_task(
                    lambda n=name: finder.apply(n, relative_path="src/hawedit/editorial_acceptance.py", depth=1)
                )
            with references.symbol_dict_grouper.disabled_context():
                callers = agent.execute_task(
                    lambda n=name: references.apply(n, relative_path="src/hawedit/editorial_acceptance.py")
                )
            records.append({"symbol": name, "definition": definition, "references": callers})
        destination = root / "specs/evidence-based-studio/serena-T8-authority-research-map.json"
        if destination.exists():
            raise RuntimeError("Refusing to overwrite an actual research map")
        destination.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        print(f"Captured {len(records)} actual signed-study/authority records", flush=True)
    finally:
        agent.on_shutdown()


if __name__ == "__main__":
    main()
