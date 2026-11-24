# Swarm prompt for Gemini in Antigravity — finish the #1 task sheet (2026-11-18)

Paste everything below the line into the **lead** agent. The lead starts the other agents and
gives each one its lane section, word for word.

---

You are the **lead** of a small team of coding agents finishing HawEdit, a Sorani (ckb) video
repurposing system. The work is defined in the task sheet:

`C:\Users\Wareen\.gemini\antigravity\scratch\HawEdit\specs\pro-grade-program\gemini-task-sheet-2026-11-18.md`

Read it completely before doing anything. Everything in its section 0 ("Rules before anything
else") binds you and every agent you start. This prompt only adds how to split the work safely.
Where the two disagree, the task sheet and the repo's `AGENTS.md` win.

## 1. Set up (lead only, before starting anyone)

1. Make one integration worktree and branch:
   `git -C C:\Users\Wareen\.gemini\antigravity\scratch\HawEdit worktree add ..\HawEdit-swarm -b gemini/number-one fix/kurdish-rtl-captions`
2. Copy the task sheet and this prompt into `HawEdit-swarm\specs\pro-grade-program\` and commit
   them there first. They are untracked in the original checkout, so no worktree has them
   otherwise. Never edit, commit, push or rebase `fix/kurdish-rtl-captions` or the original
   checkout: another agent owns them and pull request HawzhinBlanca/HawEdit#25.
3. Each lane gets its own worktree, branched from `gemini/number-one`:
   `git worktree add ..\HawEdit-lane-<n> -b gemini/lane-<n> gemini/number-one`
4. Run `bash scripts/setup.sh` inside **every** worktree. Do not borrow another checkout's
   `.venv`: it may import that checkout's `src/`, so your tests would silently run someone
   else's code. Check with `.venv/Scripts/python.exe -c "import hawedit; print(hawedit.__file__)"`.
5. Read `D:\HawEdit-media\README.md`. That folder is the real test media. Nobody writes into
   `sources/`.

## 2. Shared-resource rules (the machine is one PC)

HawaPC01: 64 CPU threads, two RTX 3090 Ti (24 GB each). A full gate takes ~46 min alone.

- **One full gate at a time, run by the lead only**, on `gemini/number-one`. Lanes run
  `bash scripts/verify.sh --fast` plus the pytest files their change touches. A lane never claims
  a task is done; it hands the branch to the lead.
- **GPU:** at most one ASR/GPU job per card. Lane 1 owns GPU 0, lane 2 owns GPU 1
  (`CUDA_VISIBLE_DEVICES`). Other lanes do not start GPU work.
- **Numbers that must not collide:** ADRs (`## D-NNN` in `DECISIONS.md`) and blockers
  (`## #NN` in `BLOCKED.md`). Lane 1 uses D-336–D-339, lane 2 D-340–D-343, lane 3 D-344–D-347,
  lane 4 D-348–D-351, lane 5 D-352–D-355. A lane that needs a blocker number asks the lead; the
  next free one is #27.
- **Files several lanes want:** `src/hawedit/pipeline.py`, `DECISIONS.md`, `BLOCKED.md`,
  `PROGRESS.md`. Keep edits to them small and late, and say in `impact-map.md` exactly which
  lines you touch. The lead merges in the order of section 4 and resolves conflicts; a lane
  never force-pushes or rewrites another lane's commits.
- **Floors:** lanes never commit `scripts/test-count.floor` or `scripts/coverage.floor`. Only
  the lead's gate run on the integration branch moves them, and the lead commits them as
  `chore(gate)` before pushing.

## 3. The lanes

Each lane follows the repo loop: Research → Plan (stop for `Approved-by:`) → Implement test-first.
**Owner approval is the bottleneck, so batch it:** every lane writes research and plan for its
first task, then the lead collects all plans into one message to the owner (one paragraph per
plan, the `[HAWA]` questions listed separately) instead of five separate interruptions.

### Lane 1 — Real reels (critical path; task sheet Phase A)
A2 → A4 → A5. Start with the 5-minute excerpt in `D:\HawEdit-media\excerpts\`, then the 40-min
AI episode. First deliverable: the exact gate or stage that stops a real run today and why
(A2), with the log. Then ten reels from the AI episode in `D:\HawEdit-media\reels\<run>\`, with
wall time per stage in `evidence/`. Measure 4K VP9 decode cost before anything else; if it is too
slow, derive a 1440p copy into `excerpts/`. A3 (parking the heavy runtime controls) and A6
(licence) are owner decisions: write the question, do not act.

### Lane 2 — Speech (task sheet Phase B)
B1 first: profile one real ASR run on the AI episode, per stage, into `evidence/`. No speed work
before that file exists. Then B2 (final ASR only on chosen clips, padded) and B6 (validator on
vs off, measured WER on the same clips). B3 needs the owner (third-party audio, key); B5 needs
reference text (#1). Write those questions for the lead.

### Lane 3 — Selection (task sheet Phase C; no GPU)
C1 (sentence numbers instead of milliseconds; removes the 4,000-word table in `path_a.py`), then
C4 (topic-segmentation candidates, MIT method, no code copied from AGPL projects), then C5
(pairwise ranking replacing the asserted weights in `judge.py`). Use the teasers that open each
episode (README) as a first check: do selected moments overlap the human editor's picks? Mark
the teaser source times by hand before scoring; say how they were marked.

### Lane 4 — Picture (task sheet Phase D; no GPU)
D6 (`\kf` highlight direction inside Sorani words, libass #406) and D7 (Latin fallback font),
proven with rendered frame sequences. Then D5 (bigger 2–3-word captions off faces, tables and
the burned-in teaser label) and D8 (30 ms fades at cuts). New golden images need the owner's
approval, as D-334's did. D1/D2 (YuNet, active speaker) wait for lane 2's speaker labels and an
owner decision on the model file (`models/**` is read-only for agents); write the request.

### Lane 5 — Review and scoreboard (task sheet Phases A7, E, F3; no GPU)
A7 first: `evidence/usable-rate.csv` and a one-command way to add a reel's verdict. Then E1
(contact sheet per reel: first frame, both sides of every cut, an enlarged caption crop) and E3
(hard edit rules checked in code: never cut inside a word, 30–200 ms padding, duration bounds).
Wire or delete the unwired `render_critic.py`; do not add a third critic.

## 4. Lead: merge and finish

1. Merge order: lane 1, then 5, 2, 3, 4. Each merge goes into `gemini/number-one` as a merge
   commit (no squash, no rebase of others' work).
2. After each merge: `bash scripts/verify.sh` on the integration branch. Green → flip that
   task's rows with `bash scripts/update-ledger.sh <feature> <T1,T2,...> <tests>` (several rows
   per call is fine). Red → send the failure back to the lane; do not fix it yourself in a way
   that hides it.
3. Push `gemini/number-one` and open a pull request against `main` only after the owner says so.
   "Done" is the gate green **and** CI green on that pull request **and**, for anything a viewer
   sees, a reel in `D:\HawEdit-media\reels\` that the owner has watched and scored in
   `evidence/usable-rate.csv`.
4. Stop the swarm and report when: Phase A's "done when" is met; or every remaining task waits on
   the owner; or two consecutive merges turn the gate red for reasons the lanes cannot fix.

## 5. Report to the owner (lead only)

One message per round, short, in this order: reels produced (paths) and their scores; what
merged (commit, gate result line); measurements with provenance; each `[HAWA]` question in one
sentence; what is not verified. No adjectives in place of numbers. Earlier agents on this repo
wrote "autonomous", "masterpiece" and "10/10" with nothing behind them; the owner will check.
