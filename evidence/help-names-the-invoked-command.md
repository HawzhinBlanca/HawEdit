# Help names the invoked command — 2026-08-10

## Contract

Every module declared in `[project.scripts]` supports two user-visible forms:

- its generated console launcher, whose help must name that installed command; and
- `python -m hawedit.<module>`, whose help must name that pasteable module command.

A fixed `ArgumentParser(prog=...)` cannot satisfy both.

## Scope derived from the package

At this revision the test reads nine declarations directly from `pyproject.toml`:

1. `hawedit`
2. `hawedit-asr-bench`
3. `hawedit-asr-setup`
4. `hawedit-credentials`
5. `hawedit-editorial-bench`
6. `hawedit-fetch-models`
7. `hawedit-ffmpeg-setup`
8. `hawedit-release`
9. `hawedit-wsl-vex`

`tests/test_claims.py` also requires the list in `AUDIT_REPORT.md` to equal the declarations in
both directions.

## Windows artifact check

The readiness checkout's generated launchers were invoked directly. Representative first lines:

```text
hawedit --help
usage: hawedit [-h] [--work-dir WORK_DIR] ...

python -m hawedit.pipeline --help
usage: python -m hawedit.pipeline [-h] [--work-dir WORK_DIR] ...

hawedit-credentials --help
usage: hawedit-credentials [-h] [--check]

hawedit-release --help
usage: hawedit-release [-h] [--project-root PROJECT_ROOT] ...
```

The canonical source test is broader than the locally generated scripts: it imports and drives
all nine current modules, derives each launcher name from the package declaration, and tests a
suffixless launcher, a Windows `.exe` launcher and the `python -m` form. The hosted Linux 3.12
gate runs the same native-path test; this closes the upstream regression whose Windows literal
was not a POSIX path separator.
