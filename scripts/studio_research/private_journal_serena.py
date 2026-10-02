"""Fresh actual Serena definitions/references for the frozen private-journal unit."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    config_module = importlib.import_module("serena.config.serena_config")
    agent_module = importlib.import_module("serena.agent")
    tool_module = importlib.import_module("serena.tools")
    config = config_module.SerenaConfig.from_config_file().with_headless_mode_overrides()
    config.language_backend = config_module.LanguageBackend.LSP
    agent = agent_module.SerenaAgent(project=str(root), serena_config=config)
    targets = {
        "src/hawedit/studio_private.py": [
            "_private",
            "PrivateSqlitePath/__init__",
            "PrivateSqlitePath/_verify_binding",
            "PrivateSqlitePath/verify",
        ],
        "src/hawedit/studio_billing.py": [
            "GuardedGeminiTransport/__init__",
            "GuardedGeminiTransport/path",
            "GuardedGeminiTransport/_connection",
            "GuardedGeminiTransport/_send",
            "GuardedGeminiTransport/_call",
        ],
        "tests/test_studio_private.py": [
            "directory_alias",
            "test_studio_private_new_journal_is_owner_private",
            "test_studio_private_parent_normalization_refused",
            "test_studio_private_real_wal_crash_recovers_without_deleting_evidence",
        ],
        "tests/test_studio_billing.py": [
            "private_billing_path",
            "seed_private_file",
            "guard",
            "test_studio_billing_private_root_required_before_any_egress",
            "test_studio_billing_linked_database_refused",
            "test_studio_billing_database_replacement_during_count_refuses_generation",
            "test_studio_billing_root_replacement_after_response_retains_uncertainty",
            "test_studio_billing_storage_drift_refuses_both_egress_routes",
        ],
    }
    evidence = []
    try:
        finder = agent.get_tool(tool_module.FindSymbolTool)
        references = agent.get_tool(tool_module.FindReferencingSymbolsTool)
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
                    {
                        "file": path,
                        "symbol": name,
                        "definition": definition,
                        "references": callers,
                    }
                )
        destination = root / "specs/evidence-based-studio/serena-T3-private-final-map.json"
        destination.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(f"Captured {len(evidence)} fresh Serena symbol/caller records", flush=True)
    finally:
        agent.on_shutdown()


if __name__ == "__main__":
    main()
