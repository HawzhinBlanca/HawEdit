# README quality-bar binding — 2026-08-10

Two front-door claims are now derived rather than maintained by memory:

1. `README.md` says `gate` is the strict required status check on protected `main` exactly while
   `BLOCKED.md` #7 is resolved. The assertion is symmetric: reopening the blocker while leaving
   the claim is as red as deleting the claim while the blocker remains resolved.
2. The `cli.py` module-map row names every callable exported by `hawedit.cli.__all__`:
   `use_utf8_streams`, `machine_readable_stdout` and `program_name`.

The live branch-protection measurement remains recorded in `BLOCKED.md` #7. This evidence does not
pretend a local unit test can query a protected repository setting without credentials; it binds
the two checked-in claims and leaves the hosted setting to its recorded API evidence.
