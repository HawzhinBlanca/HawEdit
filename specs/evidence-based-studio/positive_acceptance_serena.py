"""Actual reusable release/study evidence definitions and callers; research only."""

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
    targets = {
        "src/hawedit/release_approval.py": (
            "_project_identity", "_validate_gate", "_candidate", "_hosted_release",
            "_attestation_command", "_attestations", "_verify_signature", "verify_release_approval",
        ),
        "src/hawedit/editorial_acceptance.py": (
            "VerifiedEditorialStudy", "_CandidateRecord", "_inventory", "_freeze_study_items",
            "_review_packet", "_verify_signature", "_load_review", "_load_approval",
            "_load_adjudication", "evaluate_editorial_study", "validate_acceptance_split",
            "partition_episode_disjoint",
        ),
        "src/hawedit/qc.py": ("QcRecord",),
        "src/hawedit/delivery.py": ("promote_candidate",),
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
        destination = root / "specs/evidence-based-studio/serena-T8-positive-evidence-research-map.json"
        if destination.exists():
            raise RuntimeError("Refusing to overwrite actual positive-path research")
        destination.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        print(f"Captured {len(records)} actual positive acceptance research records", flush=True)
    finally:
        agent.on_shutdown()


if __name__ == "__main__":
    main()
