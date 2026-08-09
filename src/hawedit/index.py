"""§2 text retrieval — BM25 over words **and** character 3-grams of normalized Sorani.

§2: "BM25 + character 3-grams over the normalized transcript. Character n-grams matter more
than usual — Sorani is morphologically rich with heavy clitic attachment, so word-level
matching misses variants a human reads as identical."

The n-gram field is not a refinement of the word field, it is load-bearing. Kurdish attaches
possessives, definiteness and copulas directly onto the stem: a speaker who says `کتێبەکەم`
("my book") has produced a token that word-level BM25 shares nothing with `کتێب` ("book").
Query the stem against a word-only index and it returns nothing, for a match any Kurdish
speaker considers obvious. The two fields are scored separately and combined, so the
contribution of each is visible on every hit and the balance is tunable — see D-016.

**Kurdish invariant #3 lives here.** Both factories accept a `NormalizedTranscript`, never
raw. The runner uses one document per sentence: a one-document episode index has no passages
to rank and its only hit spans the whole media (D-164).

Everything here is exact and in-memory — §6 notes the 256 GB is load-bearing and expects the
transcript index to live in RAM. No approximate structures, and no dependency: BM25 over an
episode's sentences is a dictionary of postings.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final

from hawedit.normalize import normalize_sorani
from hawedit.sentences import Sentence
from hawedit.transcripts import NormalizedTranscript, RawTranscript, assert_model_input

__all__ = [
    "DEFAULT_B",
    "DEFAULT_K1",
    "DEFAULT_NGRAM_SIZE",
    "DEFAULT_NGRAM_WEIGHT",
    "Bm25Index",
    "Document",
    "SearchHit",
    "character_ngrams",
    "index_tokens",
]

# Okapi BM25's usual constants. k1 controls how fast term frequency saturates, b how hard
# document length is normalized. These are the standard defaults and are exposed rather than
# baked in, because §8.2 tunes retrieval against real candidates, not against convention.
DEFAULT_K1: Final = 1.2
DEFAULT_B: Final = 0.75

# §2 says character 3-grams specifically.
DEFAULT_NGRAM_SIZE: Final = 3

# How much the n-gram field contributes relative to the word field. Chosen so exact word
# matches still outrank pure morphological overlap while clitic variants remain findable —
# see D-016. A tunable, not a constant to trust.
DEFAULT_NGRAM_WEIGHT: Final = 0.5

# Word-boundary sentinels for n-gram padding, so a stem at the start of a word produces a
# distinct gram from the same letters mid-word.
_WORD_START: Final = "\x02"
_WORD_END: Final = "\x03"

_WHITESPACE = re.compile(r"\s+")


def _strip_punctuation(token: str) -> str:
    """Drop leading/trailing punctuation, keeping Kurdish letters and digits."""
    return "".join(char for char in token if not unicodedata.category(char).startswith("P")).strip()


def index_tokens(text: str) -> tuple[str, ...]:
    """Normalize `text` (§4.1) and split it into indexable word tokens."""
    normalized = normalize_sorani(text)
    tokens = (_strip_punctuation(part) for part in _WHITESPACE.split(normalized))
    return tuple(token for token in tokens if token)


def character_ngrams(word: str, size: int = DEFAULT_NGRAM_SIZE) -> tuple[str, ...]:
    """Character n-grams of one word, padded at both boundaries.

    Padding matters for clitic attachment: `کتێب` standing alone and `کتێب` at the head of
    `کتێبەکەم` share their interior grams but differ at the trailing boundary, so an exact
    word match still scores higher than a morphological relative.
    """
    if size < 1:
        raise ValueError("n-gram size must be at least 1")
    padded = f"{_WORD_START}{word}{_WORD_END}"
    if len(padded) < size:
        return (padded,)
    return tuple(padded[i : i + size] for i in range(len(padded) - size + 1))


@dataclass(frozen=True, slots=True)
class Document:
    """One indexed unit — a sentence or segment of **normalized** transcript."""

    doc_id: str
    text_norm: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One retrieved document, with each field's contribution kept separate."""

    doc_id: str
    score: float
    word_score: float
    ngram_score: float
    start_ms: int
    end_ms: int


@dataclass
class _Field:
    """One BM25 field: postings, document lengths, and the stats scoring needs."""

    postings: dict[str, dict[str, int]] = field(default_factory=dict)
    lengths: dict[str, int] = field(default_factory=dict)

    @property
    def average_length(self) -> float:
        return sum(self.lengths.values()) / len(self.lengths) if self.lengths else 0.0

    def add(self, doc_id: str, terms: Sequence[str]) -> None:
        self.lengths[doc_id] = len(terms)
        for term, count in Counter(terms).items():
            self.postings.setdefault(term, {})[doc_id] = count

    def score(self, query_terms: Sequence[str], k1: float, b: float) -> dict[str, float]:
        """Okapi BM25 over this field, returning a score per matching document."""
        total_documents = len(self.lengths)
        if not total_documents:
            return {}
        average = self.average_length
        scores: dict[str, float] = {}
        for term in query_terms:
            posting = self.postings.get(term)
            if not posting:
                continue
            document_frequency = len(posting)
            idf = math.log(
                1.0 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            for doc_id, frequency in posting.items():
                length_norm = 1.0 - b + b * (self.lengths[doc_id] / average if average else 1.0)
                contribution = idf * (frequency * (k1 + 1.0)) / (frequency + k1 * length_norm)
                scores[doc_id] = scores.get(doc_id, 0.0) + contribution
        return scores


class Bm25Index:
    """§2's text index: BM25 over words, plus BM25 over character n-grams."""

    def __init__(
        self,
        documents: Iterable[Document],
        k1: float = DEFAULT_K1,
        b: float = DEFAULT_B,
        ngram_size: int = DEFAULT_NGRAM_SIZE,
        ngram_weight: float = DEFAULT_NGRAM_WEIGHT,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.ngram_size = ngram_size
        self.ngram_weight = ngram_weight
        self.documents: tuple[Document, ...] = tuple(documents)

        seen: set[str] = set()
        self._by_id: dict[str, Document] = {}
        self._words = _Field()
        self._ngrams = _Field()

        for document in self.documents:
            if document.doc_id in seen:
                raise ValueError(
                    f"duplicate document id {document.doc_id!r}: every hit referring to it "
                    f"would be ambiguous about which passage matched."
                )
            seen.add(document.doc_id)
            self._by_id[document.doc_id] = document

            tokens = index_tokens(document.text_norm)
            if not tokens:
                raise ValueError(
                    f"document {document.doc_id!r} has no indexable text. An empty document "
                    f"drags the average length down and can never be retrieved."
                )
            self._words.add(document.doc_id, tokens)
            self._ngrams.add(
                document.doc_id,
                [gram for token in tokens for gram in character_ngrams(token, self.ngram_size)],
            )

    @staticmethod
    def from_transcript(
        transcript: NormalizedTranscript,
        *,
        k1: float = DEFAULT_K1,
        b: float = DEFAULT_B,
    ) -> Bm25Index:
        """Index one normalized transcript only for episode-level mention checks.

        This shape cannot retrieve a passage: every query can return only the same document,
        whose window is the whole episode. Use `from_sentences` for ranked retrieval.

        Raises:
            TypeError: a raw transcript was passed (Kurdish invariant #3).
        """
        assert_model_input(transcript)
        if isinstance(transcript, RawTranscript):  # pragma: no cover - assert_model_input raises
            raise TypeError("raw transcript passed to the index")
        end_ms = transcript.words[-1].end_ms if transcript.words else 0
        return Bm25Index(
            [
                Document(
                    doc_id=transcript.media_id,
                    text_norm=transcript.text_ckb,
                    start_ms=transcript.words[0].start_ms if transcript.words else 0,
                    end_ms=end_ms,
                )
            ],
            k1=k1,
            b=b,
        )

    @staticmethod
    def from_sentences(
        sentences: Sequence[Sentence],
        transcript: NormalizedTranscript,
        *,
        k1: float = DEFAULT_K1,
        b: float = DEFAULT_B,
    ) -> Bm25Index:
        """Index each sentence as its own document, normalizing on the way in.

        `Sentence.text` holds raw surface forms — invariant #1 keeps them that way — so the
        normalization happens here, explicitly, rather than being assumed upstream. One
        document per sentence is what lets a hit hand Stage 5 a real time window instead of
        a whole episode. The normalized transcript—not a bare media id—keeps invariant #3 on
        the factory the runner actually uses.

        Raises:
            TypeError: a raw transcript was passed (Kurdish invariant #3).
        """
        assert_model_input(transcript)
        media_id = transcript.media_id
        return Bm25Index(
            [
                Document(
                    doc_id=f"{media_id}#{position}",
                    text_norm=normalize_sorani(sentence.text),
                    start_ms=sentence.start_ms,
                    end_ms=sentence.end_ms,
                )
                for position, sentence in enumerate(sentences)
            ],
            k1=k1,
            b=b,
        )

    def search(self, query: str, limit: int = 10) -> tuple[SearchHit, ...]:
        """Retrieve documents matching `query`, best first.

        The query is normalized (§4.1) before scoring, so an Arabic-keyboard query matches
        Kurdish-keyboard text. Word and n-gram scores are combined as
        `word + ngram_weight * ngram`, and both survive onto the hit so the balance can be
        tuned against real candidates in §8.2 rather than guessed.

        Ties break on document id, so re-running a query never reshuffles a candidate list.

        Raises:
            ValueError: the query has no indexable terms, or `limit` cannot return a hit.
        """
        if limit < 1:
            raise ValueError(
                f"limit={limit} cannot return a document; negative slicing silently drops "
                "tail hits instead of selecting a best-prefix"
            )
        query_tokens = index_tokens(query)
        if not query_tokens:
            raise ValueError(
                f"query {query!r} has no indexable terms after normalization — an empty "
                f"query would silently return the whole index or nothing at all."
            )
        if not self.documents:
            return ()

        word_scores = self._words.score(query_tokens, self.k1, self.b)
        query_grams = [
            gram for token in query_tokens for gram in character_ngrams(token, self.ngram_size)
        ]
        ngram_scores = self._ngrams.score(query_grams, self.k1, self.b)

        hits: list[SearchHit] = []
        for doc_id in set(word_scores) | set(ngram_scores):
            word_score = word_scores.get(doc_id, 0.0)
            ngram_score = ngram_scores.get(doc_id, 0.0)
            document = self._by_id[doc_id]
            hits.append(
                SearchHit(
                    doc_id=doc_id,
                    score=word_score + self.ngram_weight * ngram_score,
                    word_score=word_score,
                    ngram_score=ngram_score,
                    start_ms=document.start_ms,
                    end_ms=document.end_ms,
                )
            )

        hits.sort(key=lambda hit: (-hit.score, hit.doc_id))
        return tuple(hits[:limit])
