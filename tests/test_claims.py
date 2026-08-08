"""What the documentation claims must be true of the code — audit findings #1 and #10.

Two of the ten audit findings were not code defects at all. `README.md` opened with
"Implements BLUEPRINT.md v1.1", which a reader takes as *the system is built*; and two ledger
rows were marked DONE whose stated Definition of Done was not met — §4.1 normalization with
one of five collisions unimplemented, and a "diarization benchmark" that was the metric with
no benchmark behind it.

Prose drifts from code silently, which is exactly why it needs tests rather than care. The
checks here are deliberately narrow: each one pins a specific claim to a specific fact that a
future change would flip — in both directions, so the ledger cannot be right while a test here
is red. That is not hypothetical: the M0.3 check below held the row at PARTIAL until §4.1's
fifth collision was actually implemented (M1.7), then failed until the row was promoted.
"""

from __future__ import annotations

import re
from pathlib import Path

from hawedit.normalize import normalize_sorani

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
PROGRESS = (ROOT / "PROGRESS.md").read_text(encoding="utf-8")


def _ledger_row(task: str) -> str:
    """The PROGRESS.md row for one task id, e.g. "M0.3"."""
    for line in PROGRESS.splitlines():
        if line.startswith(f"| {task} |"):
            return line
    raise AssertionError(f"no ledger row for {task} in PROGRESS.md")


def _status(task: str) -> str:
    cells = [c.strip() for c in _ledger_row(task).split("|")]
    return cells[3]


# --- #10 a DONE mark must be backed by the thing it claims -------------------------------


def test_the_ledger_tracks_whether_all_five_collisions_are_handled() -> None:
    """§4.1 lists five collisions. The ledger's mark on M0.3 must follow the code, both ways.

    The probe is a token that *should* separate — an inflected noun with a conjunctive `و`
    joined on. D-003's `وتو` is the wrong probe: it is ambiguous, the rule declines it by
    design, and it therefore reads as "unimplemented" forever.
    """
    handled = normalize_sorani("وکتێبەکان") == "و کتێبەکان"
    status = _status("M0.3")
    if handled:
        assert status == "DONE", (
            "conjunctive `و` separation is implemented (M1.7), so §4.1's fifth collision is "
            f"handled — M0.3 is still marked {status}. Promote it and record the evidence."
        )
    else:
        assert status != "DONE", (
            "M0.3 claims §4.1 normalization is done, but conjunctive `و` separation — one of "
            "the five collisions §4.1 lists — leaves input unchanged."
        )


def test_the_diarization_benchmark_is_not_marked_done_without_a_benchmark() -> None:
    """M0.10's Definition of Done says "DER on Kurdish multi-speaker material".

    Metric code is not a benchmark result. The evidence for a run is a file recording the
    numbers; until one exists the row cannot be DONE.
    """
    evidence = ROOT / "evidence" / "diarization-benchmark.md"
    if not evidence.exists():
        assert _status("M0.10") != "DONE", (
            "M0.10 claims a diarization benchmark on Kurdish multi-speaker material, but no "
            f"result is recorded at {evidence.relative_to(ROOT)}. The metric being implemented "
            "and the benchmark having been run are different facts."
        )


def test_every_ledger_row_marked_partial_names_its_shortfall() -> None:
    """PARTIAL without a named shortfall is DONE with extra steps."""
    for line in PROGRESS.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) > 4 and cells[3] == "PARTIAL":
            assert "Shortfall" in cells[4], f"PARTIAL row names no shortfall:\n{line}"


def _blocked_entries() -> dict[str, bool]:
    """Every BLOCKED.md entry number, mapped to whether it is still live.

    An entry keeps its heading after it is resolved — the record of what was in the way is
    worth more than a tidy file — so "resolved" is a property of the heading, not its absence.
    """
    blocked = (ROOT / "BLOCKED.md").read_text(encoding="utf-8")
    live: dict[str, bool] = {}
    for number, rest in re.findall(r"^##\s*#(\d+)([^\n]*)", blocked, re.MULTILINE):
        resolved = "RESOLVED" in rest.upper()
        live[number] = live.get(number, True) and not resolved
    return live


def test_every_blocked_row_points_at_a_live_blocked_entry() -> None:
    """A BLOCKED row must cite a blocker that exists **and is still in the way**.

    Checking only for existence is not enough, and this test was written because it was not
    enough: `BLOCKED.md` #5 (an ffmpeg with libass and HarfBuzz) was resolved on 2026-08-06,
    and M2.4 sat marked BLOCKED behind it for two days. That is audit finding #10's shape
    exactly — a status that stopped tracking reality — but pointing the other way: work that
    was ready and looked impossible, rather than work that was incomplete and looked done.
    """
    entries = _blocked_entries()
    for line in PROGRESS.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) > 4 and cells[3] == "BLOCKED":
            cited = set(re.findall(r"`BLOCKED\.md`\s*#(\d+)", cells[4]))
            assert cited, f"BLOCKED row cites no entry:\n{line}"
            missing = cited - entries.keys()
            assert not missing, (
                f"{cells[1]} cites BLOCKED.md #{sorted(missing)}, which does not exist. "
                f"Entries present: {sorted(entries)}"
            )
            resolved = {n for n in cited if not entries[n]}
            assert resolved != cited, (
                f"{cells[1]} is marked BLOCKED, but every blocker it cites is resolved "
                f"(#{sorted(resolved)}). The work is available — re-status the row."
            )


# --- #1 the README must not describe a product that does not exist -----------------------


def test_the_readme_names_what_blocks_a_runnable_product() -> None:
    """§3 Stage 1 turns audio into a transcript, and nothing downstream can start without one.

    While no ASR adapter exists, the README has to say so in its own words near the top — not
    leave it to be inferred from a milestone table. The first version of this test pinned an
    exact sentence and went stale the moment the sentence stopped being true; this one asks the
    filesystem what is missing and requires the README to agree.
    """
    asr_adapter = ROOT / "src" / "hawedit" / "omniasr.py"
    opening = README.split("## Setup")[0]
    if not asr_adapter.exists():
        assert "Stage 1" in opening, (
            "no ASR adapter exists, so nothing can produce a transcript — the README's opening "
            "must name Stage 1 as what stands between this and a runnable product."
        )
        assert "transcript" in opening.lower()
    else:
        assert "Stage 1" not in opening or "runs" in opening, (
            f"{asr_adapter.name} exists, so the README should no longer present Stage 1 as the "
            f"blocker."
        )


def test_the_readme_does_not_open_by_claiming_the_blueprint_is_implemented() -> None:
    paragraph = README.lstrip().split("\n\n", 2)[1]
    assert not paragraph.startswith("Implements"), (
        f"the README opens by claiming the blueprint is implemented: {paragraph!r}"
    )


def test_every_stage_the_readme_calls_not_written_really_has_no_module() -> None:
    """The status table must not go stale in the optimistic direction.

    Stage 3 and Stage 4 are listed as not written. If someone builds one and forgets the
    README, this fails — understating what exists is a smaller sin than overstating it, but
    the table is only trustworthy if it tracks in both directions.
    """
    not_written = {
        "3": ROOT / "src" / "hawedit" / "discovery.py",
        "4": ROOT / "src" / "hawedit" / "judge.py",
    }
    for stage, module in not_written.items():
        row = next(line for line in README.splitlines() if line.startswith(f"| {stage} ·"))
        claims_absent = "not written" in row
        assert claims_absent == (not module.exists()), (
            f"README says Stage {stage} is {'not written' if claims_absent else 'written'}, "
            f"but {module.name} {'exists' if module.exists() else 'does not exist'}"
        )


def test_every_shell_command_the_readme_offers_exists() -> None:
    """A README that tells you to run a script that was renamed is a broken promise."""
    for script in set(re.findall(r"bash (scripts/[\w.-]+\.sh)", README)):
        assert (ROOT / script).exists(), f"README offers `bash {script}`, which does not exist"


def test_every_module_invocation_the_readme_offers_is_importable() -> None:
    from importlib.util import find_spec

    for module in set(re.findall(r"python -m (hawedit[\w.]*)", README)):
        assert find_spec(module) is not None, f"README offers `python -m {module}`, which is not"


def test_every_module_the_readme_maps_exists() -> None:
    """The module map is the README's most load-bearing table; a stale row misdirects."""
    for name in set(re.findall(r"^\| `(\w+\.py)` \|", README, re.MULTILINE)):
        assert (ROOT / "src" / "hawedit" / name).exists(), f"module map lists missing {name}"


def test_the_module_map_covers_every_module() -> None:
    mapped = set(re.findall(r"^\| `(\w+\.py)` \|", README, re.MULTILINE))
    on_disk = {p.name for p in (ROOT / "src" / "hawedit").glob("*.py")} - {"__init__.py"}
    assert on_disk <= mapped, f"modules absent from the README map: {sorted(on_disk - mapped)}"


# =========================================================================================
# §10's attribution obligation, and the workflow the README names
#
# §10 lists "Attribution obligations — Community-1 (CC-BY-4.0) requires an attribution notice
# in shipped product docs" as a known risk with a stated mitigation. The mitigation was a
# hand-maintained list in the README beside a sentence claiming a function generated it. It
# did not: the function emitted libass/LGPL, which the README omitted, and the README listed
# the OFL font, which the function omitted because a font is not a §7 model.
# =========================================================================================


def test_every_generated_attribution_notice_appears_in_the_readme() -> None:
    from hawedit.registry import attribution_notices

    section = README.split("## Attribution")[1]
    missing = [n for n in attribution_notices() if _attribution_subject(n) not in section]
    assert not missing, f"attribution obligations absent from the README: {missing}"


def test_every_readme_attribution_bullet_is_generated() -> None:
    """Both directions. A bullet nobody generates is a bullet that outlives its obligation."""
    from hawedit.registry import attribution_notices

    section = README.split("## Attribution")[1].split("\n##")[0]
    documented = {
        line.split("—")[0].strip(" -`") for line in section.splitlines() if line.startswith("- ")
    }
    generated = {_attribution_subject(n) for n in attribution_notices()}
    assert documented == generated, (
        f"README-only: {sorted(documented - generated)}; generated-only: "
        f"{sorted(generated - documented)}"
    )


def _attribution_subject(notice: str) -> str:
    return notice.split("—")[0].strip(" `")


def test_the_shipped_font_carries_its_licence_beside_it() -> None:
    """OFL-1.1 requires the licence to accompany the font. A missing OFL.txt is a licence
    violation in every build that ships the .ttf."""
    fonts = ROOT / "assets" / "fonts"
    assert (fonts / "NotoNaskhArabic-Regular.ttf").exists()
    assert (fonts / "OFL.txt").exists(), "the font ships without the licence it requires"


def test_the_docs_name_workflows_that_exist() -> None:
    """The README and BLOCKED.md both pointed at `.github/workflows/hawedit.yml`; the file is
    `gate.yml`.

    `DECISIONS.md` is excluded on purpose: it is append-only history, and an entry recording
    that a name *used to be* wrong must keep quoting the wrong name.
    """
    on_disk = {p.name for p in (ROOT / ".github" / "workflows").glob("*.y*ml")}
    for doc in ("README.md", "BLOCKED.md", "PROGRESS.md"):
        named = set(re.findall(r"\.github/workflows/([\w.-]+\.ya?ml)", (ROOT / doc).read_text()))
        assert named <= on_disk, (
            f"{doc} names workflows that do not exist: {sorted(named - on_disk)}"
        )


# =========================================================================================
# The gate is green here and on a clean runner, or it is not a gate
#
# CI installs `.[dev,media]` — §6 puts Stage 0 on CPU and the CUDA build of torch is ~2 GB of
# runner disk for kernels nothing in the gate calls. So every distribution in the `gpu` extra
# is ABSENT there and present on hawapc01, and `mypy --strict` therefore checks two different
# programs in the two places.
#
# It has already diverged once: four errors on the runner — three `import-not-found` and one
# `unused-ignore` — against `Success` locally, for imports added across four iterations that
# were never pushed. D-067.
# =========================================================================================


# The two modules that import the `gpu` extra. Checked directly rather than by reasoning about
# `pyproject.toml`: an indirect check on the config passed while the real condition still failed,
# which is the same mistake this whole finding is about.
_GPU_IMPORTING_MODULES = ("src/hawedit/video_input.py", "src/hawedit/qwen_visual.py")


def test_the_gpu_modules_typecheck_with_the_gpu_extra_absent() -> None:
    """`mypy --strict` must pass on a machine without the `gpu` extra, because CI is one.

    This is the check that would have caught D-067 locally. It runs the real type checker with
    `--no-site-packages`, which reproduces "the package is not installed" exactly, over the only
    two modules that import the extra. Four errors were live on the runner while `verify.sh`
    printed VERIFY OK here: three `import-not-found` and one `unused-ignore`.

    Scoped to those two files on purpose. Run over all of `src`, `--no-site-packages` is
    *stricter* than CI — CI installs `media`, so `numpy` and `cv2` resolve there — and silencing
    those would throw away the stubs numpy ships.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--no-site-packages",
            # Without this the run reuses `.mypy_cache` from the ordinary gate typecheck, which
            # was made WITH the packages installed — so this test reported success while the
            # condition it exists to reproduce was still broken. Found by mutating the override
            # away and watching it pass.
            "--no-incremental",
            *_GPU_IMPORTING_MODULES,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "mypy --strict fails when the gpu extra is absent, which is how CI runs:\n"
        f"{result.stdout}{result.stderr}\n"
        "Every import of an optional dependency needs an `ignore_missing_imports` override in "
        "pyproject.toml, and no `# type: ignore` may depend on the package being installed."
    )


# =========================================================================================
# The ledger has to account for every module, and the docs for the survivor floor
#
# `test_the_module_map_covers_every_module` above binds the README's map to the filesystem,
# and it passes. PROGRESS.md had no equivalent, and eight modules had drifted out of it —
# `visual_pipeline.py` and `reframe.py` described in floating prose blocks *after* the tables
# with no filename and no status mark, the other six unmentioned. A module with no status is
# invisible to the DONE/PARTIAL/BLOCKED tally the ledger exists to publish, so "35 DONE" was
# counting a smaller program than the one that ships.
# =========================================================================================


def _ledger_rows() -> list[list[str]]:
    """Every `| Mx.y | deliverable | STATUS | evidence |` row, split into cells."""
    marks = {"DONE", "PARTIAL", "WIP", "TODO", "BLOCKED"}
    rows = []
    for line in PROGRESS.splitlines():
        if not re.match(r"^\| M\d+\.\d+ \|", line):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) > 4 and cells[3] in marks:
            rows.append(cells)
    return rows


def test_the_ledger_accounts_for_every_module() -> None:
    """A module named only in prose, or not at all, is a module with no recorded status.

    Deliberately reads the *evidence* cell of a row whose *status* cell is a legend mark, not
    the file as a whole: a mention in a floating amendment below the table is exactly the
    failure this catches, because it leaves the module out of the published tally.
    """
    claimed: set[str] = set()
    for cells in _ledger_rows():
        claimed |= set(re.findall(r"(\w+\.py)", " ".join(cells[4:])))
    on_disk = {p.name for p in (ROOT / "src" / "hawedit").glob("*.py")} - {"__init__.py"}
    assert on_disk <= claimed, (
        f"modules with no status in any PROGRESS.md ledger row: {sorted(on_disk - claimed)}. "
        "Add a row, or name the module in an existing row's evidence cell — a description in "
        "prose after the table does not put it in the DONE/PARTIAL tally."
    )


def test_no_document_promises_that_short_media_keeps_every_scene() -> None:
    """`rerank_and_keep` refuses media with fewer windows than §3's survivor floor.

    Three documents said the opposite — that short media keeps all its scenes — which is the
    single most consequential doc/code contradiction in the repo: it describes a graceful
    degradation the code deliberately does not do, so a reader sizing a job would expect
    output where they get a refusal.
    """
    from hawedit.visual_index import KEEP_MIN

    forbidden = re.compile(
        r"(all scenes on shorter|short(er)? media keeps all|keeps? (all|every) "
        r"(available )?scenes?)",
        re.IGNORECASE,
    )
    for name in ("README.md", "AUDIT_REPORT.md", "PROGRESS.md", "DECISIONS.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        hits = [m.group(0) for m in forbidden.finditer(text)]
        assert not hits, (
            f"{name} says short media keeps every scene; `rerank_and_keep` raises below "
            f"{KEEP_MIN} survivors instead: {hits}"
        )


def test_the_readme_describes_the_gate_floor_as_tests_that_passed() -> None:
    """`gate.py` compares `evidence.passed`, not `collected`.

    The two differ by exactly the skips, which is the case the floor exists to catch — a
    README promising a floor on *collected* tests describes a ratchet that a creeping skip
    condition would slide straight through.
    """
    gate = (ROOT / "src" / "hawedit" / "gate.py").read_text(encoding="utf-8")
    assert "if evidence.passed < floor:" in gate, "gate.py no longer gates on passed"
    sentence = next(
        (line for line in README.splitlines() if "test-count.floor" in line),
        None,
    )
    assert sentence is not None, "the README no longer describes scripts/test-count.floor"
    # The claim itself, not the absence of a word: the prose around it is free to contrast the
    # two, and an earlier version of this test failed on that contrast.
    claim = re.search(r"test-count\.floor`\s+tests\s+\*{0,2}(\w+)", sentence)
    assert claim is not None, f"the README states no floor unit: {sentence.strip()!r}"
    assert claim.group(1) == "passed", (
        f"the README calls the floor a count of tests {claim.group(1)}: {sentence.strip()!r} — "
        "gate.py gates on tests that passed"
    )


def test_every_test_count_in_the_audit_is_dated() -> None:
    """An audit figure is a measurement at an instant; unlabelled, it reads as current.

    The first version of this test asserted the count *equalled* `scripts/test-count.floor`.
    That was wrong twice over: it went red the moment anyone added a test — pressuring the next
    person to edit a historical document or delete the check — and it misstated the defect. The
    audit's 1,063 was not wrong because 1,063 differs from today's floor; it was wrong because
    nothing on the line said when it was true. So require the date and let the number age.
    """
    audit = (ROOT / "AUDIT_REPORT.md").read_text(encoding="utf-8")
    undated = [
        line.strip()
        for line in audit.splitlines()
        if re.search(r"[\d,]{3,} (?:collected|passed)", line)
        and not re.search(r"\d{4}-\d{2}-\d{2}", line)
    ]
    assert not undated, (
        "AUDIT_REPORT.md quotes a test count with no measurement date, so it reads as a claim "
        f"about the suite as it stands today: {undated}. Date it, or drop the figure."
    )


def test_every_data_file_the_wheel_ships_is_tracked_by_git() -> None:
    """A file that exists only on the machine that wrote it is not a file this project has.

    `models/revisions.json` shipped exactly that way: `models/*` is git-ignored, `git add -A`
    skipped it in silence, the local gate passed against a file the runner never received, and
    CI failed on `no pinned revisions found`. The same trap already had a `!models/sources.json`
    exception and a comment explaining it — which is why this is a test now rather than a
    third comment.

    Reads `[tool.setuptools.data-files]`, so anything added to the wheel is covered without
    anyone remembering to extend a list here.
    """
    import subprocess
    import tomllib

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    shipped = [
        Path(rel)
        for paths in pyproject["tool"]["setuptools"]["data-files"].values()
        for rel in paths
    ]
    assert shipped, "no data-files declared; this test would assert nothing"
    tracked = {
        Path(line)
        for line in subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.splitlines()
    }
    untracked = [str(p) for p in shipped if p not in tracked]
    assert not untracked, (
        f"the wheel ships {untracked}, which git does not track — so it exists on this machine "
        "and on no other. Add a `!` exception in .gitignore and commit the file."
    )
