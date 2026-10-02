"""Actual Serena/LSP definitions and references for private storage adoption."""

from __future__ import annotations

import importlib
import json
import sys
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
            "StudioStorageError", "PrivateDirectory", "PrivateDirectory/__init__",
            "PrivateDirectory/verify", "PrivateDirectory/child", "PrivateDirectory/check_file",
            "PrivateDirectory/member_identity", "PrivateDirectory/open_new_file",
            "PrivateDirectory/remove_owned", "PrivateDirectory/sync", "write_text_atomic",
            "PrivateSqlitePath", "PrivateSqlitePath/__init__",
        ],
        "src/hawedit/studio_submissions.py": [
            "SubmissionStore", "SubmissionStore/__init__", "SubmissionStore/_connection",
            "SubmissionStore/work_dir",
        ],
        "src/hawedit/studio_uploads.py": [
            "_probe", "UploadStore", "UploadStore/__init__", "UploadStore/_verify",
            "UploadStore/_record", "UploadStore/_write", "UploadStore/_reserved",
            "UploadStore/begin", "UploadStore/receive", "UploadStore/status",
            "UploadStore/describe", "UploadStore/source", "UploadStore/_validated_source",
        ],
        "src/hawedit/web.py": [
            "_upload_store", "HawEditWebHandler/do_POST", "HawEditWebHandler/do_PUT",
            "HawEditWebHandler/do_GET", "run_web_server",
        ],
        "tests/test_studio_storage.py": [
            "test_studio_upload_accepts_actual_supported_containers",
            "test_studio_native_server_uploads_use_private_startup_storage",
            "test_studio_http_unconfigured_upload_storage_refuses",
            "test_studio_http_lost_upload_root_refuses_without_recreation",
        ],
        "tests/studio_test_storage.py": [
            "create_private_test_root", "make_private_directory", "seed_private_file",
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
                evidence.append({"file": path, "symbol": name,
                                 "definition": definition, "references": callers})
        destination = root / "specs/evidence-based-studio" / sys.argv[1]
        if destination.exists():
            raise RuntimeError("Refusing to overwrite earlier Serena evidence")
        destination.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(f"Captured {len(evidence)} actual fresh definitions/reference records", flush=True)
    finally:
        agent.on_shutdown()


if __name__ == "__main__":
    main()
