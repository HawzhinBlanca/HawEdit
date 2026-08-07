# Evidence — §4.1 collision incidence on real Sorani

**Task:** M0.15 · **Date:** 2026-08-06 · **Reproduce:**
`.venv/bin/python scripts/measure_collisions.py`

§0 asserts that skipping normalization means "your search index silently fails to match text
that looks identical on screen". This is the first measurement of that claim on real Kurdish
in this project.

## Corpus

KLPT's bundled Sorani hunspell dictionary, `klpt/data/ckb-Arab.dic` — **24,894 entries,
24,051 distinct forms**. CC-BY-SA-4.0 (D-002).

**Read the caveat before the numbers.** This is a *curated lexicon*, not text people typed.
It is close to already-normalized, so the collisions §4.1 warns about are almost absent by
construction. Every figure below is therefore a **floor**, not an estimate of what real
Kurdish transcripts and comment text will contain. Real typed material is where `ه`+ZWNJ and
Arabic-keyboard `ي`/`ك` actually live, and measuring that needs the corpus M0.12 is blocked
on. This corpus was used because it is the only real Sorani reachable from this container
(BLOCKED.md #6).

## Result

| Measure | Value |
|---|---|
| Items altered by normalization | **0.84%** (209 / 24,894) |
| Distinct raw forms | 24,051 |
| Distinct forms after normalization | 24,000 |
| **Forms that would have failed to match** | **0.21%** (51 merges) |

Per-collision incidence (items containing each, not occurrences):

| Collision | In §4.1's table | Items |
|---|---|---|
| `ه` + ZWNJ vs `ە` | yes | 0 |
| Arabic `ي` | yes | 0 |
| Arabic `ك` | yes | 1 |
| Farsi numerals | yes | 0 |
| Eastern Arabic numerals | yes | 0 |
| **`ھ` U+06BE vs `ه` U+0647** | **no** | **204** |

## The finding: a collision §4.1 does not list

Every merge in a curated dictionary came from one pair the blueprint's §4.1 table omits —
**U+06BE ARABIC LETTER HEH DOACHASHMEE against U+0647 ARABIC LETTER HEH**:

```
ئاهەنگ | ئاھەنگ      بەرهەم | بەرھەم      جیهان | جیھان
بەهار  | بەھار        دهۆک   | دھۆک        سەرهەنگ | سەرھەنگ
```

These are ordinary, high-frequency Kurdish words — *Duhok*, *world*, *spring*, *product*.
KLPT resolves the collision, so §4.1's mandate covers it in practice; §4.1's *table* does
not mention it, so nobody reading the blueprint would know to test for it.

It is also **contextual**: KLPT rewrites `ھ` → `ه` inside a word but leaves an isolated `ھ`
alone. That asymmetry is pinned by a test, because a library update that changes it would
silently shift every index key without failing anything.

## What this justifies

- §4.1 stays MANDATORY, now with a number behind it rather than an assertion.
- `heh_doachashmee` is added to the measured collision set (D-013).
- 0.21% on clean data is the floor. The measurement to act on is the same script run over
  real transcripts — which is one of the things M0.12 is waiting for.
