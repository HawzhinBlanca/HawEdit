"""Capture reproducible Serena symbol and caller evidence before studio edits."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "src/hawedit/web.py": [
        "JobInfo",
        "JobInfo/to_dict",
        "JobManager",
        "JobManager/__init__",
        "JobManager/_load_persisted_jobs",
        "JobManager/_save_job",
        "JobManager/submit_job",
        "JobManager/_run_job_stages",
        "JobManager/update_job_caption",
        "JobManager/get_all_jobs",
        "JobManager/get_job",
        "HawEditWebHandler",
        "HawEditWebHandler/do_POST",
        "HawEditWebHandler/do_GET",
        "run_web_server",
    ],
    "src/hawedit/pipeline.py": ["build_parser", "_build_and_run", "PipelineRun"],
    "src/hawedit/durable_workflow.py": ["configure_dbos", "run_durable"],
    "src/hawedit/delivery.py": ["promote_candidate", "reconcile_delivery"],
    "src/hawedit/clip.py": ["QcRecord"],
}


def main() -> None:
    # Run with the configured Serena runtime, not HawEdit's locked production environment.
    config_module = importlib.import_module("serena.config.serena_config")
    agent_module = importlib.import_module("serena.agent")
    tool_module = importlib.import_module("serena.tools")
    config = config_module.SerenaConfig.from_config_file().with_headless_mode_overrides()
    config.language_backend = config_module.LanguageBackend.LSP
    agent = agent_module.SerenaAgent(project=str(ROOT), serena_config=config)
    destination = ROOT / "specs" / "evidence-based-studio" / "serena-map.json"
    evidence: list[dict[str, Any]] = (
        json.loads(destination.read_text(encoding="utf-8")) if destination.exists() else []
    )
    try:
        finder = agent.get_tool(tool_module.FindSymbolTool)
        references = agent.get_tool(tool_module.FindReferencingSymbolsTool)
        for path, names in TARGETS.items():
            for name in names:
                if any(item["file"] == path and item["symbol"] == name for item in evidence):
                    continue
                with finder.symbol_dict_grouper.disabled_context():
                    symbol = agent.execute_task(
                        lambda n=name, p=path: finder.apply(n, relative_path=p, depth=1)
                    )
                with references.symbol_dict_grouper.disabled_context():
                    callers = agent.execute_task(
                        lambda n=name, p=path: references.apply(n, relative_path=p)
                    )
                evidence.append(
                    {"file": path, "symbol": name, "definition": symbol, "references": callers}
                )
                destination.write_text(
                    json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
                )
        print(f"Mapped {len(evidence)} symbols with Serena", flush=True)
    finally:
        agent.on_shutdown()


if __name__ == "__main__":
    main()
