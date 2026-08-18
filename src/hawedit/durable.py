"""The `hawedit-durable` CLI: parse and validate argv, then hand off to the durable workflow.

Deliberately thin, and deliberately free of any import that needs the `agentic` extra
installed. `durable_workflow.py` carries the actual `@DBOS.step()`/`@DBOS.workflow()` — see its
module docstring for why `dbos` cannot be a deferred, function-local import the way every other
optional dependency in this codebase is. That constraint would otherwise make `--help` require
`dbos` too, and a `--help` invocation is supposed to be a pure no-op regardless of what is
installed. So the import lives inside `main`, after argument validation has already exited on
`-h`/`--help` or a bad flag combination — measured on a clean wheel install with none of the
optional extras: before this split, `hawedit-durable --help` raised `ModuleNotFoundError: No
module named 'dbos'`.
"""

from __future__ import annotations

import json
import sys

from hawedit.cli import machine_readable_stdout, program_name, use_utf8_streams
from hawedit.pipeline import _BUILD_ERRORS, build_parser

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """`python -m hawedit.durable <same argv as hawedit.pipeline> [--run-id ID]`.

    Same CLI surface as `hawedit.pipeline.main`, run through the durable workflow. `--run-id` is
    this module's one addition — consumed here, never seen by `build_parser` — for exercising
    or relying on the duplicate-submission guarantee from a shell. Exit code matches
    `hawedit.pipeline.main`: 0 complete, 1 incomplete, 2 refused before any work started.
    """
    use_utf8_streams()
    raw = list(argv if argv is not None else sys.argv[1:])
    run_id: str | None = None
    if "--run-id" in raw:
        at = raw.index("--run-id")
        if at + 1 >= len(raw):
            print("✗ --run-id requires a value", file=sys.stderr)
            return 2
        run_id = raw[at + 1]
        del raw[at : at + 2]

    # `-h`/`--help` — and any argparse-level usage error — must exit here, before anything
    # touches DBOS (or even imports it). `build_parser()`'s own `prog` names `hawedit.pipeline`
    # unconditionally (every other console script builds its own parser instead of sharing this
    # one); overridden here so `--help` under this entry point reads `hawedit.durable`.
    early = build_parser()
    early.prog = program_name("hawedit.durable")
    early.parse_args(raw)

    # Deferred past the point `-h`/a bad flag would already have exited — see the module
    # docstring for why this import cannot move to the top of the file.
    from hawedit.durable_workflow import run_durable

    # The one JSON document promised on stdout shares that stream with every library `--gemini`/
    # `--visual`/`--omni-asr` load, and D-119 already measured what one bare `print` from
    # `transformers` does to it. `machine_readable_stdout()` is `pipeline.main`'s own fix for
    # exactly this; reused here rather than re-derived, since the risk is identical — this
    # module runs the same producer wiring, only durably.
    with machine_readable_stdout() as report_stream:
        try:
            payload = run_durable(raw, run_id=run_id)
        except _BUILD_ERRORS as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 2

        print(json.dumps(payload, ensure_ascii=False, indent=2), file=report_stream)
    return 0 if payload.get("complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
