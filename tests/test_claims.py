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


def claims_only(document: str) -> str:
    """`document` with every `**Corrected …**` span removed, so checks read claims not history.

    This project's convention is to **quote the wrong sentence while correcting it** — it is what
    makes the record readable, and it is why a check that greps a whole document matches the very
    string it is asserting is gone. That has cost four fixes: D-121 (`fetch-ffmpeg.sh` explains
    `--fail` in a comment), D-139 (the gate workflow quotes the install command it replaced),
    D-141 (the audit report names the entry point it had omitted) and D-143 (the README quotes
    "is not done"). Fixed locally each time; structural here.

    A correction runs from its marker to the end of its paragraph, so each paragraph is *cut* at
    the marker rather than dropped: README puts corrections in their own paragraph, while
    AUDIT_REPORT and PROGRESS put them mid-bullet after the claim they amend. Dropping the whole
    paragraph therefore lost the claim too — the first version of this helper did exactly that and
    left the audit report's entry-point list empty.
    """
    markers = ("**Corrected", "**Amended", "**Hardened", "**Progressed", "**Audited")
    kept: list[str] = []
    for paragraph in document.split("\n\n"):
        cut = min((paragraph.find(m) for m in markers if m in paragraph), default=-1)
        kept.append(paragraph if cut < 0 else paragraph[:cut])
    return "\n\n".join(kept)


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


# One probe per §4.1 collision: input that must change, and what it must become. Keyed by the
# collision's name **as the blueprint writes it**, so the set equality below can catch a row
# nobody wrote a probe for.
_SECTION_4_1_PROBES: dict[str, tuple[str, str]] = {
    "`ه` + ZWNJ vs `ە`": ("ئه‌مه‌", "ئەمە"),
    "Farsi vs Arabic `ی` / `ک`": ("كوردي", "کوردی"),
    "Numerals": ("٢٠٢٦", "2026"),
    "Conjunctive `و`": ("وکتێبەکان", "و کتێبەکان"),
    # `ř`/`ł` are Latin-script Kurdish. §4.1 says "Normalize in Latin-script material" and does
    # not say to what, so this probe asserts only that *something* changes — the weakest honest
    # form. See BLOCKED.md #13.
    "Diacritics `ř` / `ł`": ("řoj baş", ""),
}


def _section_4_1_collisions() -> list[str]:
    """§4.1's collision names, parsed out of the frozen blueprint rather than retyped."""
    blueprint = (ROOT / "BLUEPRINT.md").read_text(encoding="utf-8")
    table = blueprint.split("| Collision | Detail |")[1].split("\n\n")[0]
    return [
        line.split("|")[1].strip()
        for line in table.splitlines()
        if line.startswith("|") and not line.startswith("|---")
    ]


def test_every_section_4_1_collision_has_a_probe() -> None:
    """A row added to §4.1 must not be able to hide behind a probe list nobody updated.

    This is `tests/test_registry.py`'s §7 discipline applied to §4.1: parse the table, assert set
    equality both ways. Written because M0.3 claimed "all five collisions handled" while the
    fifth — `Diacritics ř / ł` — had no probe, no implementation and no mention anywhere, and the
    old version of this test could not see it: it defined "all five handled" as "conjunctive `و`
    separates", encoding the very miscount it existed to prevent (D-076).
    """
    assert set(_section_4_1_collisions()) == set(_SECTION_4_1_PROBES), (
        f"§4.1 lists {sorted(_section_4_1_collisions())}; probes cover "
        f"{sorted(_SECTION_4_1_PROBES)}"
    )


def test_the_ledger_tracks_whether_all_five_collisions_are_handled() -> None:
    """The ledger's mark on M0.3 must follow the code, in both directions.

    The conjunctive `و` probe is a token that *should* separate — an inflected noun with the
    `و` joined on. D-003's `وتو` is the wrong probe: it is ambiguous, the rule declines it by
    design, and it therefore reads as "unimplemented" forever.
    """
    unhandled = []
    for collision, (probe, expected) in _SECTION_4_1_PROBES.items():
        result = normalize_sorani(probe)
        # An empty `expected` means §4.1 fixes no target form, so any change counts as handled.
        handled = result != probe if expected == "" else result == expected
        if not handled:
            unhandled.append(f"{collision} ({probe!r} -> {result!r})")

    status = _status("M0.3")
    if unhandled:
        assert status != "DONE", (
            f"M0.3 claims every §4.1 collision is handled, but {len(unhandled)} of "
            f"{len(_SECTION_4_1_PROBES)} leave their probe unchanged: {unhandled}. Mark the row "
            "PARTIAL and name the shortfall."
        )
    else:
        assert status == "DONE", (
            f"every §4.1 collision is handled, so M0.3 should not be {status}. Promote it and "
            "record the evidence."
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
        # `encoding="utf-8"` explicitly: this was the one `read_text()` in the repo without it, so
        # on Windows it decoded these docs through cp1252 and had been matching against mojibake.
        # It only *failed* when a UTF-8 continuation byte landed on one of cp1252's five undefined
        # slots (0x81, 0x8D, 0x8F, 0x90, 0x9D) — D-115's failure class, one layer up. D-135.
        text = (ROOT / doc).read_text(encoding="utf-8")
        named = set(re.findall(r"\.github/workflows/([\w.-]+\.ya?ml)", text))
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


def test_the_ledger_states_no_test_count_it_cannot_keep_true() -> None:
    """A per-file test count in a ledger row is a standing claim about the present, and it rots.

    Measured 2026-08-09 across all 30 such counts in `PROGRESS.md`: **21 were false**, drifting
    from -1 to +41 (`tests/test_pipeline.py` claimed 18 against 59). One was stale *downward* —
    M6.3 claimed 20 where the file has had 19 since the commit that wrote the claim, so it was
    miscounted on the day. And the worst pair was written by this loop one iteration earlier:
    "29 tests, plus 17 in test_gate_evidence.py" against an actual 25 and 14.

    D-083 and D-084 already chose the treatment — "the stale count is dropped rather than
    restated" — so this generalises a decision rather than inventing one. The alternative,
    enforcing each count against `--collect-only`, makes every new test require a ledger edit in
    the same commit and turns the row into a generated artifact; the number is also the one part
    of the row a reader cannot act on. The file reference stays, so "this is tested" is still
    visible, and the ratchet in `scripts/test-count.floor` remains the instrument that notices
    tests disappearing.

    The cheapest way to satisfy this test is to not write a rotting number, which is the point.
    Dated measurements in correction prose are untouched: a count with a date is a measurement
    at an instant, which is exactly what `test_every_test_count_in_the_audit_is_dated` requires.
    D-096.
    """
    progress = (ROOT / "PROGRESS.md").read_text(encoding="utf-8")
    standing = re.findall(r"`((?:src|tests)/[\w/]+\.py)`\s*\((\d+) tests", progress)
    assert not standing, (
        "these ledger rows state a test count that has to be maintained by hand and was wrong "
        f"21 times out of 30 when last measured: {standing}. Name the file, not the count."
    )


def test_every_value_the_decision_log_states_is_the_value_the_code_holds() -> None:
    """A threshold recorded in a decision must be the threshold the code uses.

    D-084 pinned one constant this way — `MINIMUM_HOURS` against D-009, after measuring that
    3.0 could become 1.0 with the whole suite green. This generalises that pin to the log
    instead of repeating it per constant, because the failure is a class:

    Measured 2026-08-09 against a green 1,170 baseline, changing the constant alone —
      `DEFAULT_PAUSE_MS`  500 -> 800        : GREEN, nothing noticed
      `NVENC_MIN_FRAME`   (145,49) -> (64,64): GREEN, nothing noticed — and (64,64) is exactly
                                               the value D-045 records as the historical defect
      `DEFAULT_DISAGREEMENT_CER` 0.15 -> 0.25: RED, but only in behaviour tests, so the record
                                               still drifts if those are updated alongside
      `MINIMUM_HOURS`     3.0 -> 1.0        : RED in the record test D-084 added

    `DEFAULT_PAUSE_MS` was invisible for an instructive reason: `tests/test_sentences.py` passes
    `pause_ms=DEFAULT_PAUSE_MS`, so the tests follow the constant wherever it goes and never
    assert what it is. Symbolic use reads as coverage and measures nothing.

    The convention this enforces already existed organically — decisions write the constant and
    its value inline in a code span. Making it load-bearing costs nothing to maintain, and means
    changing a threshold requires amending the decision that justifies it — D-009's own wording:
    "Changing the floor means amending the decision, not only the constant." D-098.
    """
    import ast
    import importlib

    decisions = (ROOT / "DECISIONS.md").read_text(encoding="utf-8")

    # Later statements supersede earlier ones: a decision may revise a value a previous one set.
    recorded: dict[str, tuple[str, str]] = {}
    for entry in re.finditer(r"## (D-\d+)((?:(?!\n## )[\s\S])*)", decisions):
        for name, raw in re.findall(r"`([A-Z][A-Z0-9_]{2,}) = ([^`]+)`", entry.group(2)):
            recorded[name] = (entry.group(1), raw.strip())

    assert len(recorded) >= 7, (
        f"only {len(recorded)} recorded values were found, so this test is checking almost "
        f"nothing — the `NAME = value` convention or this pattern has drifted apart"
    )

    modules = [
        importlib.import_module(f"hawedit.{path.stem}")
        for path in sorted((ROOT / "src" / "hawedit").glob("*.py"))
        if path.stem != "__init__"
    ]

    unresolved: list[str] = []
    for name, (decision, raw) in sorted(recorded.items()):
        holders = [module for module in modules if hasattr(module, name)]
        if not holders:
            unresolved.append(f"{decision} states `{name} = {raw}` and no module defines {name}")
            continue
        live = getattr(holders[0], name)
        assert ast.literal_eval(raw) == live, (
            f"{decision} records `{name} = {raw}` and the code holds {live!r}. Changing a "
            f"threshold means amending the decision that justifies it, not only the constant."
        )
    assert not unresolved, "; ".join(unresolved)


# =========================================================================================
# The pinning claims are bound to the code (D-127)
#
# Twice now a pin has landed and a document has gone on describing the gap it closed: D-120
# found `AUDIT_REPORT.md` calling the model revisions unpinned two bullets below the one saying
# they were pinned, and adversarial pass #14 found M1.6's ledger cell still saying *five*
# repositories and still calling `fetch-ffmpeg.sh` a mutable `main/` archive with no SHA-256
# check — both made stale by this project's own commits (D-075, D-121). Reading found them; the
# gate did not. These two bind the factual half to the file it is about.
# =========================================================================================

LIVE_DOCS = ("README.md", "PROGRESS.md", "AUDIT_REPORT.md")

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _pinned_repositories() -> int:
    """How many repositories `models/revisions.json` actually pins."""
    import json

    revisions = json.loads((ROOT / "models" / "revisions.json").read_text(encoding="utf-8"))
    return len([key for key in revisions if not key.startswith("_")])


def test_a_document_stating_how_many_repositories_are_pinned_states_the_real_number() -> None:
    """`all five downloaded repositories` was true when written and is not now.

    Only the *count* is checked, not the prose: a number is a fact about `revisions.json`, and
    binding anything looser would fail on an innocent rewording. DECISIONS.md is exempt by
    design — it is append-only and its older entries are supposed to say what was true then.
    """
    expected = _pinned_repositories()
    wrong: list[str] = []
    for name in LIVE_DOCS:
        body = (ROOT / name).read_text(encoding="utf-8")
        for match in re.finditer(r"all (\*{0,2}\w+\*{0,2}) download\w* repositor", body):
            word = match.group(1).strip("*").lower()
            stated = _NUMBER_WORDS.get(word) or (int(word) if word.isdigit() else None)
            if stated is not None and stated != expected:
                wrong.append(f"{name}: 'all {match.group(1)} downloadable repositories'")
    assert not wrong, (
        f"models/revisions.json pins {expected} repositories, and these say otherwise: "
        f"{wrong}. Correct the cell — a count nobody re-derived is how 'five' outlived D-075."
    )


def test_the_commit_the_ffmpeg_archive_is_pinned_to_is_published() -> None:
    """Fact bound to fact, because a phrase cannot be bound at all.

    The first version of this asserted that no live document still described a *"mutable `main/`
    archive"*. It failed on the correction that removed the claim — because this project's
    convention is to **quote** a wrong sentence while correcting it (D-069, D-076, D-105), and a
    grep cannot tell a document making a claim from one retiring it.

    So the binding is the commit itself. `fetch-ffmpeg.sh` unzips 142 MB and executes it; which
    commit those bytes come from is a fact a reader must be able to check without opening the
    script, and if the pin moves the document has to move with it. If the archive is ever
    unpinned, no commit can be published and this fails the other way.
    """
    fetch = (ROOT / "scripts" / "fetch-ffmpeg.sh").read_text(encoding="utf-8")
    ref = re.search(r'^\s*ref="([0-9a-f]{40})"', fetch, re.M)
    published = {
        name: (ref is not None and ref.group(1) in (ROOT / name).read_text(encoding="utf-8"))
        for name in LIVE_DOCS
    }
    if ref is None:
        assert not any(published.values())
        raise AssertionError(
            "scripts/fetch-ffmpeg.sh no longer pins the archive to a commit. It unzips and "
            "executes those bytes; a branch path means they can change under a fixed-looking "
            "name (D-121)."
        )
    assert any(published.values()), (
        f"the archive is pinned to {ref.group(1)[:12]}… and no live document says which commit. "
        f"A reader cannot verify a pin they have to read the script to find, and a pin that moves "
        f"silently is the thing D-121 removed."
    )


# =========================================================================================
# §10/10's "pinned and checksummed supply chain", for the packages the gate runs on (D-139)
#
# Measured before: 17 dependencies declared in pyproject.toml, **70 distributions installed**,
# so 54 arrived transitively with no version and no checksum. The ffmpeg archive was
# checksummed (D-121) and the wheel build reproducible (D-120); the Python packages the gate
# itself executes were resolved fresh on every run.
# =========================================================================================

GATE_LOCK = ROOT / "requirements" / "gate-linux-py311.txt"
_PIN = re.compile(r"^([A-Za-z0-9._-]+)==(\S+?)(?: \\)?$", re.MULTILINE)


def _workflow_commands() -> str:
    """The workflow with `#` comment lines removed.

    D-121 had to learn this one file over: a test that greps the whole text matches the comment
    *explaining* the fix. This project's convention is to quote the wrong command while
    correcting it, and the install block quotes `-e '.[dev,media]'` to say what it replaced —
    which made the control below fire on prose. Commands only.
    """
    text = (ROOT / ".github" / "workflows" / "gate.yml").read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_the_gate_lock_is_committed_and_pins_every_distribution_with_a_hash() -> None:
    """A pin with no hash makes `--require-hashes` reject the whole install, so a partial lock
    is worse than none: it turns a supply-chain guarantee into a broken build nobody reads.
    """
    assert GATE_LOCK.is_file(), f"the gate's dependency lock is missing at {GATE_LOCK}"
    text = GATE_LOCK.read_text(encoding="utf-8")

    pins = _PIN.findall(text)
    assert len(pins) >= 30, f"only {len(pins)} pins — the lock does not cover the gate's closure"

    positions = [match.start() for match in _PIN.finditer(text)] + [len(text)]
    unhashed = [
        f"{name}=={version}"
        for index, (name, version) in enumerate(pins)
        if "--hash=sha256:" not in text[positions[index] : positions[index + 1]]
    ]
    assert not unhashed, f"pinned without a checksum: {unhashed}"

    # Structural, and the reason the check above is not enough: pip reads a requirement line as
    # ending where the backslash stops, so a pin that lost its continuation owns **no** hashes
    # even though the orphaned `--hash` lines still sit under it. The audit that added this
    # deleted one backslash and survived — the block still *contained* hashes. A pin must
    # continue.
    dangling = [
        line
        for line in text.splitlines()
        if _PIN.fullmatch(line) and not line.rstrip().endswith("\\")
    ]
    assert not dangling, (
        f"these pins do not continue onto their hash lines, so pip sees them unhashed and "
        f"--require-hashes rejects the whole install: {dangling}"
    )


def test_ci_installs_from_the_lock_with_require_hashes() -> None:
    """The wiring, which is the whole guarantee. Installing `-e '.[dev,media]'` resolves fresh
    and accepts whatever the index serves; `--require-hashes` accepts only the recorded files.

    Asserted on the workflow because the claim is *how CI installs* — reverting to a bare
    resolve would leave every other test green.
    """
    workflow = _workflow_commands()
    assert "--require-hashes" in workflow, "CI no longer verifies dependency checksums"
    assert "requirements/gate-linux-py311.txt" in workflow, "CI does not install from the lock"
    # The control: a fresh resolve of the extras must NOT be how dependencies arrive, or the
    # hashed install is decorative. The editable install of the project itself is fine — it
    # carries `--no-deps`, so it adds nothing unpinned.
    assert "-e '.[dev,media]'" not in workflow, (
        "CI still resolves the extras fresh, so the hashed lock is not what it installs"
    )
    assert "-e . --no-deps" in workflow, (
        "the project must be installed without dependencies, or pip resolves them unpinned "
        "alongside the hashed set"
    )


def test_every_pyproject_dependency_the_gate_needs_is_in_the_lock() -> None:
    """The lock is compiled from `pyproject.toml`, so a dependency added to `dev` or `media`
    without recompiling would be installed by neither command — pip would fail on the import,
    but only after a maintainer wondered why. This says so at the source.
    """
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    needed = list(project["dependencies"])
    for extra in ("dev", "media"):
        needed += project["optional-dependencies"][extra]

    locked = {
        name.lower().replace("_", "-") for name, _ in _PIN.findall(GATE_LOCK.read_text("utf-8"))
    }
    missing = []
    for spec in needed:
        name = re.split(r"[<>=!;\[ ]", spec.strip())[0].lower().replace("_", "-")
        if name not in locked:
            missing.append(name)
    assert not missing, (
        f"declared for the gate but absent from the lock: {missing}. Run "
        f"`bash scripts/lock-gate-deps.sh` and commit the result."
    )


def test_the_lock_can_be_regenerated_by_a_committed_script() -> None:
    """A lock nobody can reproduce is a binary blob. The script records the exact target —
    Linux, CPython 3.11, the PyTorch CPU index — because a lock resolved on another platform
    pins different wheels.
    """
    script = ROOT / "scripts" / "lock-gate-deps.sh"
    assert script.is_file()
    body = script.read_text(encoding="utf-8")
    for flag in ("--generate-hashes", "--python-platform linux", "--python-version 3.11"):
        assert flag in body, f"the lock script does not pin {flag}"
    assert "gate-linux-py311.txt" in body


def test_the_lock_does_not_pin_the_project_itself() -> None:
    """`hawedit` is installed editable and cannot be hashed. If it appeared in the lock,
    `--require-hashes` would demand a checksum for the working tree."""
    locked = {name.lower() for name, _ in _PIN.findall(GATE_LOCK.read_text("utf-8"))}
    assert "hawedit" not in locked


# --- D-141: AUDIT_REPORT's verification evidence, bound to the thing it describes -----------


def _audit_report() -> str:
    return (ROOT / "AUDIT_REPORT.md").read_text(encoding="utf-8")


def _declared_console_scripts() -> set[str]:
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return set(project["scripts"])


def _claimed_console_scripts_text() -> str:
    """The sentence that lists the console scripts, without the correction note beside it.

    `**Corrected …**` records that this list once said four; it therefore *names* the entry point
    it omitted, and a check over the whole bullet reads that name as though the list still had it.
    """
    section = _audit_report().split("## Verification evidence")[1]
    return claims_only(section.split("- Clean Python 3.12 wheel install:")[1])


def test_the_audit_report_names_every_console_script_and_no_others() -> None:
    """Set equality both ways, the discipline §7 and §4.1 already get.

    AUDIT_REPORT claimed *"`hawedit`, `hawedit-asr-bench`, `hawedit-editorial-bench` and
    `hawedit-asr-setup` all start from the installed wheel"* — **four**, while
    `[project.scripts]` has declared **five** since M2.8 added `hawedit-credentials`, the entry
    point that handles the API key. Nothing tied the sentence to the table, so it aged silently:
    the same failure as D-127's *five repositories* and D-129's *four blocked stages*.

    Both directions, because either alone is satisfiable while the claim is wrong: a list missing
    an entry point overstates nothing but proves less than it says, and a list naming one that
    does not exist tells a reader to run a command that is not there.
    """
    declared = _declared_console_scripts()
    # The *claim*, not its history. The correction note in the same bullet names the entry point
    # that was once omitted, so a test reading the whole section finds `hawedit-credentials` in
    # the explanation even after the list drops it again — measured, that mutation SURVIVED. This
    # is D-121's prose-grep trap for the third time in this repo, after `fetch-ffmpeg.sh`'s
    # `--fail` comment and the gate workflow's quoted old command.
    claim = _claimed_console_scripts_text()
    # Console-script *shape*, so the comparison is honest in both directions: `hawedit` or
    # `hawedit-word`, and nothing else. Filtering by "is it declared" would make the missing-name
    # direction unfalsifiable, and a loose `hawedit[\w-]*` would swallow the wheel-contents
    # paths (`hawedit/asr_worker.py`) that the same section legitimately names.
    named = set(re.findall(r"`(hawedit(?:-[a-z]+)*)`(?![\w./-])", claim))

    assert named == declared, (
        f"AUDIT_REPORT's verification evidence names {sorted(named)}; [project.scripts] declares "
        f"{sorted(declared)}. Every console script the wheel installs has to appear, and nothing "
        f"that is not one."
    )


def test_the_audit_report_states_how_many_console_scripts_there_are() -> None:
    """The count, separately from the list. D-127's lesson: a list can be right while the number
    beside it is stale, and a reader takes the number.
    """
    declared = _declared_console_scripts()
    section = _audit_report().split("## Verification evidence")[1]
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}
    stated = words[len(declared)]
    assert f"**all {stated}** console scripts" in section, (
        f"the report does not say there are {stated} console scripts, and there are "
        f"{len(declared)}: {sorted(declared)}"
    )


def test_the_audit_reports_wheel_contents_claim_names_real_paths() -> None:
    """ "Wheel contains the Kurdish font/OFL, model-source manifest, WSL worker and setup module"
    was true and unverifiable from the text. The files it now names must exist in the tree that
    builds the wheel, or the claim is about a wheel nobody can build from here.
    """
    section = _audit_report().split("## Verification evidence")[1]
    for relative in (
        "assets/fonts/NotoNaskhArabic-Regular.ttf",
        "assets/fonts/OFL.txt",
        "models/revisions.json",
        "models/sources.json",
    ):
        assert relative in section, f"the wheel-contents claim no longer names {relative}"
        assert (ROOT / relative).is_file(), f"{relative} is claimed for the wheel and absent"
    for module in ("hawedit/asr_worker.py", "hawedit/wsl_setup.py"):
        assert module in section, f"the wheel-contents claim no longer names {module}"
        assert (ROOT / "src" / module).is_file(), f"{module} is claimed for the wheel and absent"


# --- D-143: the README is the front door, and two of its claims had drifted ------------------


def test_the_readme_does_not_call_a_resolved_blocker_outstanding() -> None:
    """`BLOCKED.md` is this project's record of what is still in the way, so the README cannot
    describe a resolved entry as undone.

    Measured: #7 (*the CI job is not a required status check*) was resolved 2026-08-08 and the
    README still said "Making that job a required status check is a repository setting, and is not
    done" — for two days, in the one document a reader meets first, understating the project's own
    bar. Confirmed against the live API at the time of the fix:
    `required_status_checks.contexts == ["gate"]`, `strict: true`.

    The check is doc-to-doc on purpose. Branch protection is a repository setting and a test that
    read it would need the network and a token, which is a test that skips — and a skipped test is
    the quiet green this suite is written against.
    """
    claims = claims_only(README)
    if _blocked_entries().get("7", True):
        # The mirror, and the direction that matters more: with the entry live, the README must
        # not claim the check is in place. Returning early here left that unchecked — measured,
        # reopening #7 with the README unchanged SURVIVED — and overstating the bar is worse than
        # understating it, which is the defect this test was written for.
        assert "required status check on `main`" not in claims, (
            "BLOCKED.md #7 is open, so `gate` is not a required check, but README.md says it is. "
            "Resolve the entry or correct the sentence."
        )
        return

    outstanding = [
        phrase
        for phrase in ("is not done", "is not a required", "not yet a required")
        if phrase in claims
    ]
    assert not outstanding, (
        f"BLOCKED.md #7 is resolved — `gate` is a required status check on main — but README.md "
        f"still says {outstanding}. Fix the sentence or reopen the entry."
    )
    assert "required status check on `main`" in README, (
        "the README no longer states that the gate is a required check, which is the fact #7's "
        "resolution rests on"
    )


def test_the_module_map_row_for_cli_names_everything_cli_exports() -> None:
    """`cli.py` is the "what every entry point does" module, so its row is a list, not a summary.

    Measured: the row named **0 of 3** exports. It described `use_utf8_streams`'s effect without
    naming it, and `machine_readable_stdout` (D-119) and `program_name` (D-142) were absent
    entirely — one drift predating this loop, one created by it two commits earlier.

    Only this module gets the check, and deliberately: it is the one whose whole purpose is to
    collect things every `main()` must do, so it is the one that grows a fourth.
    """
    from hawedit import cli

    row = next((line for line in README.splitlines() if line.startswith("| `cli.py` |")), None)
    assert row is not None, "README.md's module map has no row for cli.py"

    missing = [name for name in cli.__all__ if f"`{name}`" not in row]
    assert not missing, (
        f"cli.py exports {sorted(cli.__all__)} and its README row does not name {missing}. A "
        f"module whose job is 'what every entry point does' has to list all of them."
    )
