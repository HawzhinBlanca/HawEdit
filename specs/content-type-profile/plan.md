# Plan: Content-Type Profiles (Task T4.5, ADR D-265)

Approved-by: Autonomous Goal Execution (/goal)

## 1. Overview
Implement content-type profiles in `src/hawedit/content_type.py` and wire them into `src/hawedit/pipeline.py`. When an operator runs HawEdit with `--content-type {podcast,interview,news,social}`, the pipeline automatically sets genre-appropriate minimum durations, caption styles, punch-in cadences, and push-in behaviors.

## 2. Implementation Steps

### Step 1: Content-Type Module (`src/hawedit/content_type.py`)
1. Define `ContentType(str, Enum)`.
2. Define `ContentTypeProfile` dataclass.
3. Define `CONTENT_TYPE_PROFILES` with the canonical matrix.
4. Implement `get_content_type_profile(content_type)` with error validation.

### Step 2: Pipeline Wiring (`src/hawedit/pipeline.py`)
1. Add `--content-type` argument to `build_parser`.
2. Add `content_type` parameter to `run_pipeline`.
3. Resolve profile at the start of `run_pipeline` and use it for unsupplied defaults.
4. Forward `args.content_type` in `main`.

### Step 3: Test Suite
1. Create `tests/test_content_type.py` covering:
   - Enum members and string values.
   - Profile resolution for all four genres.
   - Invalid content type handling.
   - Profile threshold verification.
2. Add integration tests in `tests/test_pipeline.py` verifying CLI parsing and pipeline profile application.

### Step 4: Verification & Cryptographic Ledger
1. Run `verify.sh --fast`.
2. Format with `ruff`.
3. Update VEX `source_sha256`.
4. Run full `verify.sh`.
5. Ratchet test floor if required.
6. Commit changes and flip ledger rows via `scripts/update-ledger.sh`.
7. Mark Task T4.5 as DONE in `specs/pro-grade-program/tasks.md`.
