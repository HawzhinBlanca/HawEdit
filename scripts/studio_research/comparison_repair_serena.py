"""Fresh actual symbol/caller map for the paired-rating contract repair."""

from __future__ import annotations

import importlib
import json
import sys
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
        "src/hawedit/comparison_kit.py": [
            "wilson_score_interval",
            "OptionRating",
            "OptionRating/__post_init__",
            "OptionRating/to_dict",
            "PairRating",
            "PairRating/__post_init__",
            "PairRating/from_options",
            "PairRating/schema",
            "PairRating/to_dict",
            "RaterSubmission",
            "RaterSubmission/__post_init__",
            "RaterSubmission/to_dict",
            "StudyMetrics",
            "StudyMetrics/to_dict",
            "validate_ratings",
            "generate_kurdish_rating_form",
            "format_kurdish_form_markdown",
            "analyze_study",
            "export_to_qc_records",
        ],
        "src/hawedit/visual_scorecard.py": ["compute_visual_scorecard"],
        "tests/test_comparison_kit.py": [
            "test_wilson_score_interval_properties_and_known_values",
            "test_kurdish_rating_form_structure_and_markdown_formatting",
            "test_validate_ratings_schema_and_boundaries",
            "test_analyze_study_better_than_a_team_criterion",
            "test_export_to_qc_records_integration",
        ],
    }
    records = []
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
                records.append(
                    {"file": path, "symbol": name, "definition": definition, "references": callers}
                )
        destination = root / "specs/evidence-based-studio" / sys.argv[1]
        if destination.exists():
            raise RuntimeError("Refusing to overwrite earlier actual mapping")
        destination.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        print(
            f"Captured {len(records)} fresh paired-contract definition/reference records",
            flush=True,
        )
    finally:
        agent.on_shutdown()


if __name__ == "__main__":
    main()
