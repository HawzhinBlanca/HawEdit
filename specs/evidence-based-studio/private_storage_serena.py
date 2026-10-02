"""Actual fresh symbol/caller map before protected upload/outbox adoption."""

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
        "src/hawedit/studio_private.py": ["PrivateSqlitePath", "PrivateSqlitePath/__init__"],
        "src/hawedit/studio_submissions.py": [
            "StudioStorageError", "SubmissionStore", "SubmissionStore/__init__",
            "SubmissionStore/_connection", "SubmissionStore/work_dir",
        ],
        "src/hawedit/studio_uploads.py": [
            "UploadStore", "UploadStore/__init__", "UploadStore/_record",
            "UploadStore/_write", "UploadStore/_reserved", "UploadStore/begin",
            "UploadStore/receive", "UploadStore/status", "UploadStore/describe",
            "UploadStore/source", "UploadStore/_validated_source",
        ],
        "src/hawedit/web.py": [
            "HawEditWebHandler/do_POST", "HawEditWebHandler/do_PUT",
            "HawEditWebHandler/do_GET", "run_web_server",
        ],
        "tests/test_studio_uploads.py": [
            "test_upload_status_recovers_committed_media_after_ticket_failure",
        ],
        "tests/test_studio_submissions.py": [
            "test_studio_submission_tokens_survive_reconstruction",
            "test_studio_submission_refuses_unknown_or_corrupt_database",
        ],
        "tests/test_studio_queue.py": ["prepared"],
        "tests/test_studio_generation.py": ["uploaded"],
    }
    evidence = []
    try:
        finder = agent.get_tool(tool_module.FindSymbolTool)
        references = agent.get_tool(tool_module.FindReferencingSymbolsTool)
        for path, names in targets.items():
            for name in names:
                with finder.symbol_dict_grouper.disabled_context():
                    definition = agent.execute_task(
                        lambda n=name,p=path: finder.apply(n,relative_path=p,depth=1)
                    )
                with references.symbol_dict_grouper.disabled_context():
                    callers = agent.execute_task(
                        lambda n=name,p=path: references.apply(n,relative_path=p)
                    )
                evidence.append({"file":path,"symbol":name,"definition":definition,"references":callers})
        destination = root / "specs/evidence-based-studio/serena-T3-storage-before-map.json"
        destination.write_text(json.dumps(evidence,indent=2)+"\n",encoding="utf-8")
        print(f"Captured {len(evidence)} fresh symbol/caller records",flush=True)
    finally:
        agent.on_shutdown()


if __name__ == "__main__":
    main()
