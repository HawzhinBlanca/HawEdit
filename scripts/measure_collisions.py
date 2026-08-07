#!/usr/bin/env python
"""Measure §4.1 collision incidence over a body of real Kurdish text.

Usage:
    .venv/bin/python scripts/measure_collisions.py                 # bundled KLPT lexicon
    .venv/bin/python scripts/measure_collisions.py corpus.json     # a corpus manifest

Writes its findings to stdout. Regenerate `evidence/collision-incidence.md` from this and
record any change in DECISIONS.md — the numbers there are only worth having if they are
reproducible.
"""

from __future__ import annotations

import sys
from pathlib import Path

from hawedit.collisions import measure_collisions
from hawedit.corpus import Corpus

ROOT = Path(__file__).resolve().parents[1]
KLPT_DIC = ROOT / ".venv/lib/python3.11/site-packages/klpt/data/ckb-Arab.dic"


def klpt_lexicon() -> list[str]:
    """Sorani entries from KLPT's bundled hunspell dictionary (CC-BY-SA-4.0, D-002).

    Line 0 is an entry count; entries may carry `/FLAGS` affix markers.
    """
    lines = KLPT_DIC.read_text(encoding="utf-8").splitlines()[1:]
    return [word for line in lines if (word := line.split("/")[0].strip())]


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        corpus = Corpus.load(Path(argv[1]))
        label = f"{corpus.provenance.name} ({len(corpus.items)} items)"
        texts = [item.reference_ckb for item in corpus.items]
    else:
        label = f"KLPT ckb-Arab.dic ({KLPT_DIC})"
        texts = klpt_lexicon()

    report = measure_collisions(texts, sample_groups=12)
    print(f"corpus: {label}")
    print(report.summary())
    if report.merged_groups:
        print("\nforms that normalization merges (each pair is an index miss avoided):")
        for group in report.merged_groups:
            print("  " + " | ".join(group))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
