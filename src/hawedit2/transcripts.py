"""The §4.1 transcript artifacts, and the two Kurdish invariants that govern them.

    transcript.raw.json    ← EXACTLY as ASR emitted. Never modified. Ships to client.
    transcript.norm.json   ← KLPT-normalized. Used for BM25, embeddings, model input.
    transcript.en.json     ← Auxiliary English. Retrieval and reasoning aid ONLY.

**Invariant #1 — raw is never mutated after write.** Enforced three ways, because any one
of them alone is bypassable:

1. `TranscriptStore.write_raw` refuses a second write, even with identical content. An
   idempotent-looking rewrite is how in-place editing arrives.
2. `RawTranscript` is a frozen dataclass holding a tuple of words, so there is no in-memory
   mutation path either.
3. `verify_raw_integrity` compares a sidecar SHA-256 against the file. The file is also
   chmod'd to 0o444, but that is **advisory, not a guarantee** — root ignores mode bits, and
   anything that can edit the raw file can edit the sidecar. The checksum is tamper
   *evidence*, in the same spirit as the host repo's surface manifest: it makes silent
   modification loud, it does not make it impossible.

**Invariant #3 — indexes, embeddings and model inputs read norm, never raw.** Enforced at
two levels. `RawTranscript` and `NormalizedTranscript` are distinct types, so a function
annotated to take a `NormalizedTranscript` rejects raw at typecheck time; and
`assert_model_input` catches the dynamic paths that mypy cannot see. A normalized artifact
carries the digest of the raw it came from, so a stale norm — one derived from a *different*
raw, which looks perfectly valid on inspection — is detected on read.

Provenance is checked against §7 at construction: a transcript that claims a model the
blueprint does not permit is refused rather than stored and discovered later.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hawedit2.alignment import CTC_VITERBI, assert_ctc_viterbi
from hawedit2.normalize import normalize_sorani
from hawedit2.registry import resolve

__all__ = [
    "AsrProvenance",
    "NormalizedTranscript",
    "RawTranscript",
    "RawTranscriptImmutable",
    "RawTranscriptTampered",
    "StaleNormalizedTranscript",
    "TranscriptStore",
    "Word",
    "assert_model_input",
    "normalize_transcript",
]


class RawTranscriptImmutable(RuntimeError):
    """Raised on any attempt to write a raw transcript that already exists (invariant #1)."""


class RawTranscriptTampered(RuntimeError):
    """Raised when a raw transcript on disk no longer matches its recorded digest."""


class StaleNormalizedTranscript(RuntimeError):
    """Raised when a normalized artifact was derived from a different raw transcript."""


@dataclass(frozen=True, slots=True)
class Word:
    """One aligned word. Timings come from CTC Viterbi alignment only (invariant #5)."""

    w: str
    start_ms: int
    end_ms: int
    conf: float


@dataclass(frozen=True, slots=True)
class AsrProvenance:
    """Which models produced this transcript. Every name must be in §7."""

    canonical: str
    aligner: str | None = None
    validated_by: str | None = None
    mean_logprob: float | None = None

    def __post_init__(self) -> None:
        resolve(self.canonical)
        if self.validated_by is not None:
            resolve(self.validated_by)
        if self.aligner is not None:
            assert_ctc_viterbi(self.aligner)


@dataclass(frozen=True, slots=True)
class RawTranscript:
    """The canonical artifact: exactly as ASR emitted, never modified, ships to the client."""

    media_id: str
    text_ckb: str
    words: tuple[Word, ...]
    asr: AsrProvenance

    def __post_init__(self) -> None:
        # Invariant #5: timings exist only if something admissible produced them. A
        # transcript carrying words with no declared aligner has timings from nowhere.
        if self.words and self.asr.aligner is None:
            raise ValueError(
                f"{self.media_id}: transcript carries {len(self.words)} word timings but "
                f"declares no aligner. Word timings come from {CTC_VITERBI!r} only "
                f"(Kurdish invariant #5)."
            )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, indent=2)

    def sha256(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @staticmethod
    def from_json(payload: str) -> RawTranscript:
        data: dict[str, Any] = json.loads(payload)
        return RawTranscript(
            media_id=data["media_id"],
            text_ckb=data["text_ckb"],
            words=tuple(Word(**w) for w in data["words"]),
            asr=AsrProvenance(**data["asr"]),
        )


@dataclass(frozen=True, slots=True)
class NormalizedTranscript:
    """Derived from raw via §4.1 normalization. This is what models and indexes read."""

    media_id: str
    text_ckb: str
    source_sha256: str
    words: tuple[Word, ...] = field(default=())

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, indent=2)

    @staticmethod
    def from_json(payload: str) -> NormalizedTranscript:
        data: dict[str, Any] = json.loads(payload)
        return NormalizedTranscript(
            media_id=data["media_id"],
            text_ckb=data["text_ckb"],
            source_sha256=data["source_sha256"],
            words=tuple(Word(**w) for w in data.get("words", ())),
        )


def normalize_transcript(raw: RawTranscript) -> NormalizedTranscript:
    """Derive the normalized artifact from `raw`, recording which raw it came from.

    Word timings are carried across with their *raw* surface forms: alignment keys off the
    tokens the acoustic model actually emitted (§4.2), and normalization strips and rewrites
    characters in ways that would not survive a re-tokenization.
    """
    return NormalizedTranscript(
        media_id=raw.media_id,
        text_ckb=normalize_sorani(raw.text_ckb),
        source_sha256=raw.sha256(),
        words=raw.words,
    )


def assert_model_input(transcript: NormalizedTranscript | RawTranscript) -> None:
    """Refuse a raw transcript at any model / index / embedding boundary (invariant #3).

    Raises:
        TypeError: `transcript` is raw.
    """
    if isinstance(transcript, RawTranscript):
        raise TypeError(
            "raw transcript passed to a model input: indexes, embeddings and model inputs "
            "read transcript.norm.json (Kurdish invariant #3). Call normalize_transcript() "
            "first — raw is canonical and ships to the client, it is not model input."
        )


class TranscriptStore:
    """On-disk home of the §4.1 artifact triple for one working directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def raw_path(self, media_id: str) -> Path:
        return self.root / f"{media_id}.transcript.raw.json"

    def norm_path(self, media_id: str) -> Path:
        return self.root / f"{media_id}.transcript.norm.json"

    def _digest_path(self, media_id: str) -> Path:
        return self.root / f"{media_id}.transcript.raw.sha256"

    def write_raw(self, raw: RawTranscript) -> Path:
        """Write the canonical transcript once.

        Raises:
            RawTranscriptImmutable: a raw transcript for this media_id already exists.
        """
        path = self.raw_path(raw.media_id)
        if path.exists():
            raise RawTranscriptImmutable(
                f"{path} already exists. transcript.raw.json is never modified after write "
                f"(Kurdish invariant #1) — not even with identical content. If the ASR output "
                f"genuinely changed, that is a new media_id or a new run directory."
            )
        path.write_text(raw.to_json(), encoding="utf-8")
        self._digest_path(raw.media_id).write_text(raw.sha256(), encoding="utf-8")
        path.chmod(0o444)  # advisory: root ignores this, the digest is the real evidence
        return path

    def read_raw(self, media_id: str) -> RawTranscript:
        return RawTranscript.from_json(self.raw_path(media_id).read_text(encoding="utf-8"))

    def raw_digest(self, media_id: str) -> str:
        """The digest of the raw file as it is on disk right now."""
        content = self.raw_path(media_id).read_bytes()
        return hashlib.sha256(content).hexdigest()

    def verify_raw_integrity(self, media_id: str) -> None:
        """Check the raw transcript against the digest recorded when it was written.

        Raises:
            RawTranscriptTampered: the file no longer matches.
        """
        recorded = self._digest_path(media_id).read_text(encoding="utf-8").strip()
        actual = RawTranscript.from_json(
            self.raw_path(media_id).read_text(encoding="utf-8")
        ).sha256()
        if actual != recorded:
            raise RawTranscriptTampered(
                f"{self.raw_path(media_id)} no longer matches the digest recorded at write "
                f"time (recorded {recorded[:12]}…, found {actual[:12]}…). The canonical "
                f"transcript has been modified in place — Kurdish invariant #1."
            )

    def write_norm(self, norm: NormalizedTranscript) -> Path:
        """Write the derived artifact. Unlike raw this may be rewritten — re-normalizing
        after a KLPT upgrade is a legitimate operation."""
        path = self.norm_path(norm.media_id)
        path.write_text(norm.to_json(), encoding="utf-8")
        return path

    def read_norm(self, media_id: str) -> NormalizedTranscript:
        """Read the normalized artifact, refusing one derived from a different raw.

        Raises:
            StaleNormalizedTranscript: `source_sha256` does not match the stored raw.
        """
        norm = NormalizedTranscript.from_json(self.norm_path(media_id).read_text(encoding="utf-8"))
        expected = self.read_raw(media_id).sha256()
        if norm.source_sha256 != expected:
            raise StaleNormalizedTranscript(
                f"{self.norm_path(media_id)} was derived from raw {norm.source_sha256[:12]}… "
                f"but the stored raw is {expected[:12]}…. Re-run normalization: a stale norm "
                f"looks valid on inspection, which is exactly what makes it dangerous."
            )
        return norm
