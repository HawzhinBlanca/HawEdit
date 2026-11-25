"""Fresh actual acceptance-helper definitions/references, research only."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    config_module = importlib.import_module("serena.config.serena_config")
    agent_module = importlib.import_module("serena.agent")
    tools = importlib.import_module("serena.tools")
    config = config_module.SerenaConfig.from_config_file().with_headless_mode_overrides()
    config.language_backend = config_module.LanguageBackend.LSP
    agent = agent_module.SerenaAgent(project=str(root), serena_config=config)
    targets = {
        "src/hawedit/visual_scorecard.py": [
            "ProvenanceRecord",
            "DatasetSplit",
            "EvaluationProposalRecord",
            "VisualScorecardConfig",
            "VisualScorecard",
            "VisualScorecard/is_release_eligible",
            "VisualScorecard/evaluate_leadership_claim",
            "compute_visual_scorecard",
            "assert_no_holdout_leakage",
            "compute_cluster_variance",
        ],
        "src/hawedit/comparison_kit.py": [
            "PairRating",
            "RaterSubmission",
            "BlindedStudy",
            "prepare_blind_study",
            "analyze_study",
            "export_to_qc_records",
            "wilson_score_interval",
        ],
    }
    evidence = []
    try:
        finder = agent.get_tool(tools.FindSymbolTool)
        references = agent.get_tool(tools.FindReferencingSymbolsTool)
        for path, names in targets.items():
            for name in names:
                with finder.symbol_dict_grouper.disabled_context():
                    definition = agent.execute_task(
                        lambda n=name, p=path: finder.apply(n, relative_path=p, depth=1)
                    )
                with references.symbol_dict_grouper.disabled_context():
                    callers = agent.execute_task(
                        lambda n=name, p=path: references.apply(n, relative_path=p)
                    )
                evidence.append(
                    {"file": path, "symbol": name, "definition": definition, "references": callers}
                )
        destination = root / "specs/evidence-based-studio/serena-T8-current-map.json"
        if destination.exists():
            raise RuntimeError("Refusing to overwrite earlier acceptance research")
        destination.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(f"Captured {len(evidence)} fresh acceptance definition/reference records", flush=True)
    finally:
        agent.on_shutdown()


if __name__ == "__main__":
    main()
