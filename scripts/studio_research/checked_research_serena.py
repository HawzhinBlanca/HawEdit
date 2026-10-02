"""Ground research-script relocation against actual Serena definitions and callers."""

from __future__ import annotations

import importlib
import json
import sys
from functools import partial
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    configuration = importlib.import_module("serena.config.serena_config")
    agent_module = importlib.import_module("serena.agent")
    tools = importlib.import_module("serena.tools")
    config = configuration.SerenaConfig.from_config_file().with_headless_mode_overrides()
    config.language_backend = configuration.LanguageBackend.LSP
    agent = agent_module.SerenaAgent(project=str(root), serena_config=config)
    destination = Path(sys.argv[1])
    records: list[dict[str, str]] = []
    try:
        finder = agent.get_tool(tools.FindSymbolTool)
        references = agent.get_tool(tools.FindReferencingSymbolsTool)
        for source in sorted((root / sys.argv[2]).glob("*.py")):
            path = source.relative_to(root).as_posix()
            symbols = ["main"]
            if source.name == "audit_upload_response_loss.py":
                symbols.append("LostAcknowledgementHandler")
            for symbol in symbols:
                with finder.symbol_dict_grouper.disabled_context():
                    definition = agent.execute_task(
                        partial(finder.apply, symbol, relative_path=path, depth=1)
                    )
                if not json.loads(definition):
                    raise RuntimeError(f"Actual definition not found: {path}:{symbol}")
                with references.symbol_dict_grouper.disabled_context():
                    callers = agent.execute_task(
                        partial(references.apply, symbol, relative_path=path)
                    )
                records.append(
                    {
                        "path": path,
                        "symbol": symbol,
                        "definition": definition,
                        "references": callers,
                    }
                )
        if destination.exists():
            raise RuntimeError("Refusing to overwrite actual research")
        destination.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        print(f"Captured {len(records)} actual research-script records", flush=True)
    finally:
        agent.on_shutdown()


if __name__ == "__main__":
    main()
