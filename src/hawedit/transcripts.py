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
import math
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hawedit.alignment import CTC_VITERBI, assert_ctc_viterbi
from hawedit.normalize import normalize_sorani
from hawedit.registry import resolve_role

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


_WORD_EDGE_PUNCTUATION = ".,!?;:،؛؟۔…"


@dataclass(frozen=True, slots=True)
class Word:
    """One aligned word. Timings come from CTC Viterbi alignment only (invariant #5)."""

    w: str
    start_ms: int
    end_ms: int
    conf: float

    def __post_init__(self) -> None:
        if not isinstance(self.w, str) or not self.w.strip():
            raise ValueError("word surface form must be a non-empty string")
        if (
            not isinstance(self.start_ms, int)
            or isinstance(self.start_ms, bool)
            or not isinstance(self.end_ms, int)
            or isinstance(self.end_ms, bool)
        ):
            raise ValueError("word timings must be integer milliseconds")
        if self.start_ms < 0:
            raise ValueError("word start_ms must be non-negative")
        if self.end_ms <= self.start_ms:
            raise ValueError("word end_ms must be after start_ms")
        if (
            not isinstance(self.conf, int | float)
            or isinstance(self.conf, bool)
            or not math.isfinite(float(self.conf))
            or not 0.0 <= self.conf <= 1.0
        ):
            raise ValueError("word confidence must be a finite probability in [0, 1]")


@dataclass(frozen=True, slots=True)
class AsrProvenance:
    """Which models produced this transcript. Every name must be in §7."""

    canonical: str
    aligner: str | None = None
    validated_by: str | None = None
    mean_logprob: float | None = None

    def __post_init__(self) -> None:
        # Role-checked, not merely registry-checked: a scene detector is in §7 but did not
        # transcribe anything (audit finding #8).
        resolve_role(self.canonical, frozenset({"canonical_asr"}), "the canonical ASR")
        if self.validated_by is not None:
            resolve_role(self.validated_by, frozenset({"asr_validator"}), "the ASR validator")
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
        if not isinstance(self.media_id, str) or not self.media_id.strip():
            raise ValueError("media_id must be a non-empty string")
        if not isinstance(self.text_ckb, str):
            raise ValueError("text_ckb must be a string")
        if self.text_ckb and not self.text_ckb.strip():
            raise ValueError("text_ckb must not contain only whitespace")
        if not isinstance(self.words, tuple):
            raise ValueError("raw transcript words must be a tuple")
        if not isinstance(self.asr, AsrProvenance):
            raise ValueError("raw transcript asr must be AsrProvenance")

        # Invariant #5: timings exist only if something admissible produced them. A
        # transcript carrying words with no declared aligner has timings from nowhere.
        if self.words and self.asr.aligner is None:
            raise ValueError(
                f"{self.media_id}: transcript carries {len(self.words)} word timings but "
                f"declares no aligner. Word timings come from {CTC_VITERBI!r} only "
                f"(Kurdish invariant #5)."
            )

        previous: Word | None = None
        text_cursor = 0
        for index, word in enumerate(self.words):
            if not isinstance(word, Word):
                raise ValueError(f"raw transcript word {index} is not a Word")
            if previous is not None and word.start_ms < previous.end_ms:
                raise ValueError(
                    f"{self.media_id}: word timings must be chronological and non-overlapping; "
                    f"word {index} starts at {word.start_ms} ms before the previous word ends "
                    f"at {previous.end_ms} ms"
                )
            matched_surface = word.w
            surface_at = self.text_ckb.find(matched_surface, text_cursor)
            if surface_at < 0:
                # CTC aligns lexical tokens, while ASR punctuation is a separate, unreliable
                # prediction. Existing legitimate artifacts therefore contain e.g. `کوردی.`
                # aligned against `کوردی` in the raw text. Tolerate only that edge-punctuation
                # difference; the lexical word must still occur in transcript order.
                matched_surface = word.w.strip(_WORD_EDGE_PUNCTUATION)
                if matched_surface:
                    surface_at = self.text_ckb.find(matched_surface, text_cursor)
            if surface_at < 0:
                raise ValueError(
                    f"{self.media_id}: aligned word {index} ({word.w!r}) does not appear in "
                    "text_ckb in transcript order"
                )
            text_cursor = surface_at + len(matched_surface)
            previous = word

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

    @staticmethod
    def _safe(media_id: str) -> str:
        """Refuse a media_id that could escape the store, or collide inside it.

        `media_id` reaches here from filenames and job payloads. Interpolated straight into
        a path, `../../etc/x` writes outside the store entirely — and invariant #1's
        write-once guarantee means nothing if the path it guards is attacker-chosen. Audit
        finding #9.
        """
        if not media_id or media_id in {".", ".."}:
            raise ValueError("media_id must not be empty or a path component")
        if any(sep in media_id for sep in ("/", "\\", "\x00")) or ".." in media_id:
            raise ValueError(
                f"media_id {media_id!r} contains a path separator or parent reference. "
                f"Transcript paths are derived from it, so this would write outside the "
                f"store (Kurdish invariant #1)."
            )
        return media_id

    def raw_path(self, media_id: str) -> Path:
        return self.root / f"{self._safe(media_id)}.transcript.raw.json"

    def norm_path(self, media_id: str) -> Path:
        return self.root / f"{self._safe(media_id)}.transcript.norm.json"

    def _digest_path(self, media_id: str) -> Path:
        return self.root / f"{self._safe(media_id)}.transcript.raw.sha256"

    def write_raw(self, raw: RawTranscript) -> Path:
        """Write the canonical transcript once.

        Raises:
            RawTranscriptImmutable: a raw transcript for this media_id already exists.
        """
        path = self.raw_path(raw.media_id)
        # O_EXCL protected the *writer* — two workers could not both create the file — and in
        # doing so made the name appear before the content did. A concurrent reader then hit a
        # half-written file (JSONDecodeError) or a missing sidecar (FileNotFoundError) instead
        # of the orderly refusal the code promises. So the content is written to a temporary
        # file first and `os.link` puts it in place: link is atomic, fails with EEXIST if the
        # name is taken (write-once, unchanged), and the file is complete the instant it is
        # visible. Found by the second independent review — in the code written to fix the
        # first review's race.
        payload = raw.to_json().encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        digest_path = self._digest_path(raw.media_id)
        nonce = f"{os.getpid()}.{uuid.uuid4().hex}"
        staging = path.with_name(f".{path.name}.{nonce}.tmp")
        digest_staging = digest_path.with_name(f".{digest_path.name}.{nonce}.tmp")
        digest_published = False
        raw_published = False

        try:
            staging.write_bytes(payload)
            digest_staging.write_text(digest, encoding="ascii")
            # Reserve the media_id by publishing the complete sidecar first. Crucially this
            # is itself write-once: a refused second writer must not replace the digest that
            # authenticates the already-published raw file.
            try:
                os.link(digest_staging, digest_path)
            except FileExistsError:
                raise RawTranscriptImmutable(
                    f"{path} already exists or is being written. transcript.raw.json is never "
                    "modified after write (Kurdish invariant #1) — not even with identical "
                    "content. If the ASR output genuinely changed, that is a new media_id or "
                    "a new run directory."
                ) from None
            digest_published = True

            try:
                os.link(staging, path)
            except FileExistsError:
                raise RawTranscriptImmutable(
                    f"{path} already exists. transcript.raw.json is never modified after write "
                    f"(Kurdish invariant #1) — not even with identical content. If the ASR output "
                    f"genuinely changed, that is a new media_id or a new run directory."
                ) from None
            raw_published = True
        finally:
            # If publication of the raw name failed after this writer reserved the sidecar,
            # remove only our own hard link. `samefile` prevents deleting a sidecar that an
            # external actor replaced while this writer was failing.
            if digest_published and not raw_published:
                try:
                    if digest_path.samefile(digest_staging):
                        digest_path.unlink()
                except FileNotFoundError:
                    pass
            staging.unlink(missing_ok=True)
            digest_staging.unlink(missing_ok=True)
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
        path = self.raw_path(media_id)
        try:
            recorded = self._digest_path(media_id).read_text(encoding="ascii").strip()
        except (FileNotFoundError, OSError, UnicodeError) as exc:
            raise RawTranscriptTampered(
                f"{path} has no readable digest recorded at write time. The canonical "
                "transcript cannot be verified — Kurdish invariant #1."
            ) from exc
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != recorded:
            raise RawTranscriptTampered(
                f"{path} no longer matches the digest recorded at write "
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
