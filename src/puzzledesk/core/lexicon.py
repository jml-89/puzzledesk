"""Lexicon: word storage plus the lookup structures the engines need.

For a double word square of order N we only ever deal with words of a single
length N. We keep:

  * ``wordset``  - a Python set for O(1) "is this string a valid word" checks,
                   used to test whether an induced column is a real word.
  * ``letters``  - an (M, N) uint8 array of letter indices (0..25), one row per
                   word. This lets us answer per-position pattern queries with
                   vectorised NumPy instead of scanning strings.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

import numpy as np

A = ord("a")


def encode(word: str) -> np.ndarray:
    """Map a lowercase word to an array of 0..25 letter indices."""
    return np.frombuffer(word.encode("ascii"), dtype=np.uint8) - A


def decode(codes: np.ndarray) -> str:
    """Inverse of :func:`encode`."""
    return bytes(int(c) + A for c in codes).decode("ascii")


class Lexicon:
    def __init__(self, words: list[str], scores: list[float] | None = None) -> None:
        if not words:
            raise ValueError("empty word list")
        self.n = len(words[0])
        if any(len(w) != self.n for w in words):
            raise ValueError("all words must share the same length")
        self.words = words
        self.wordset = set(words)
        # (M, N) letter-index matrix.
        self.letters = np.stack([encode(w) for w in words]).astype(np.uint8)
        # Per-word quality score (soft term in the energy). Zero if unscored.
        self.scores = np.asarray(
            scores if scores is not None else [0.0] * len(words), dtype=np.float64
        )
        self.score_map = dict(zip(self.words, self.scores.tolist(), strict=True))

    def __len__(self) -> int:
        return len(self.words)

    @classmethod
    def from_words_text(cls, text: str, length: int | None = None) -> Lexicon:
        """Parse a plain word-per-line body into a Lexicon (scores default to 0).

        Pure: the caller (an adapter) reads the file and hands us the text, so no
        path or filesystem enters the kernel. See ``adapters.file_lexicon``.
        """
        words = []
        for line in text.splitlines():
            w = line.strip().lower()
            if not w.isalpha():
                continue
            if length is not None and len(w) != length:
                continue
            words.append(w)
        # Dedupe, keep order stable for reproducibility.
        uniq = list(dict.fromkeys(words))
        return cls(uniq)

    @classmethod
    def from_scored_text(cls, text: str, length: int | None = None) -> Lexicon:
        """Parse a 'word score' per-line body (see cli/gen_scored.py) into a
        Lexicon. Pure text in, Lexicon out -- the file read happens in an adapter."""
        words, scores = [], []
        seen: set[str] = set()
        for line in text.splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            w, s = parts[0].strip().lower(), float(parts[1])
            if not w.isalpha() or w in seen:
                continue
            if length is not None and len(w) != length:
                continue
            seen.add(w)
            words.append(w)
            scores.append(s)
        return cls(words, scores)

    def filtered(self, min_score: float, max_score: float | None = None) -> Lexicon:
        """Sub-lexicon of words scoring in ``[min_score, max_score]`` (``max_score``
        ``None`` == no upper bound).

        A one-sided floor applies a *quality* bar -- filtering at the acceptance bar
        turns quality into feasibility on a smaller list (D6). A two-sided *band*
        applies a *difficulty* bar (D21): "harder" draws from the obscure band rather
        than merely lowering the floor, and a banded run still proves a difficulty
        ceiling because the search stays complete.
        """
        kept = [
            (w, s)
            for w, s in zip(self.words, self.scores.tolist(), strict=True)
            if s >= min_score and (max_score is None or s <= max_score)
        ]
        return Lexicon([w for w, _ in kept], [s for _, s in kept])

    def n_letters_at(self, word: str, pos: int) -> int:
        """How many distinct letters this lexicon still admits at position ``pos`` if
        that cell of ``word`` were blanked and the rest of ``word`` held fixed.

        ``1`` means ``word`` alone forces the letter there (a self-checking crossing);
        ``>1`` means the word does not pin it. The primitive behind structural
        checkability (``app.difficulty``); scored against the *full* solving vocabulary,
        not a bar-filtered list (a solver knows every word). See D21.
        """
        pattern: list[int | None] = [int(c) for c in encode(word)]
        pattern[pos] = None
        idx = self.matching(pattern)
        return int(np.unique(self.letters[idx, pos]).size)

    def n_candidates(self, word: str, known: Iterable[int]) -> int:
        """How many words fit ``word``'s pattern when the positions in ``known`` are
        pinned to its letters and the rest are blank. ``1`` == the pattern forces
        ``word`` (its crossings so far leave no other option). The primitive behind the
        solve-order model (``app.difficulty.solve_order``): a solver's support for an
        entry is exactly which of its cells the already-solved crossings have filled.
        Scored against the *full* solving vocabulary, like ``n_letters_at`` (D22).
        """
        fixed = set(known)
        pattern: list[int | None] = [
            int(c) if i in fixed else None for i, c in enumerate(encode(word))
        ]
        return int(self.matching(pattern).size)

    def is_word(self, s: str) -> bool:
        return s in self.wordset

    def words_matching(self, allowed: list[np.ndarray]) -> np.ndarray:
        """Return indices of words whose letter at each position is permitted by
        the corresponding 26-bool mask in ``allowed`` (length N).

        This is the bitset-style intersection: a row-word is a candidate iff, at
        every position, its letter is in that column's allowed set.
        """
        mask = np.ones(len(self.words), dtype=bool)
        for pos, allow in enumerate(allowed):
            mask &= allow[self.letters[:, pos]]
        return np.nonzero(mask)[0]

    def matching(self, pattern: list[int | None]) -> np.ndarray:
        """Return indices of words matching a fixed-letter pattern.

        ``pattern`` has length N; each entry is a 0..25 letter index (that
        position is pinned) or ``None`` (free). This is the core query for
        blocked-grid fill: a slot's pattern is the letters its crossing entries
        have already fixed, and the candidates are the words that fit. Any number
        of positions may be free.
        """
        mask = np.ones(len(self.words), dtype=bool)
        for pos, val in enumerate(pattern):
            if val is not None:
                mask &= self.letters[:, pos] == val
        return np.nonzero(mask)[0]


class _EmptyLexicon:
    """A length bucket with no qualifying words (e.g. no 2-letter word clears the
    bar). Not an error -- it just means any slot of this length is unfillable, so
    the fill solver sees zero candidates and treats the grid as UNSAT there."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.words: list[str] = []
        # Empty, but present so this bucket shares Lexicon's shape: a slot of this
        # length is unfillable, so score_map is never actually indexed.
        self.score_map: dict[str, float] = {}

    def __len__(self) -> int:
        return 0

    def matching(self, pattern: list[int | None]) -> np.ndarray:
        return np.empty(0, dtype=np.intp)

    def n_letters_at(self, word: str, pos: int) -> int:
        return 0  # no words of this length => nothing admitted here

    def n_candidates(self, word: str, known: Iterable[int]) -> int:
        return 0  # no words of this length => nothing fits


class MultiLexicon:
    """Words bucketed by length -- what a blocked grid needs, since its slots no
    longer share one length. Holds a :class:`Lexicon` per length and routes
    pattern queries to the right bucket.

    A single-length ``Lexicon`` was enough while every row and column was one
    full-length word (the fully-checked square). Black cells cut the grid into
    slots of mixed length, so fill needs 2s, 3s, 4s, ... at once.
    """

    def __init__(self, by_length: dict[int, Lexicon | _EmptyLexicon]) -> None:
        self.by_length = by_length

    def __contains__(self, length: int) -> bool:
        return length in self.by_length

    def get(self, length: int) -> Lexicon | _EmptyLexicon:
        if length not in self.by_length:
            return _EmptyLexicon(length)  # no list loaded => unfillable, not a crash
        return self.by_length[length]

    @classmethod
    def from_scored_texts(
        cls,
        text_for: Callable[[int], str],
        lengths: Iterable[int],
        min_score: float = 0.0,
        max_score: float | None = None,
    ) -> MultiLexicon:
        """Build one bucket per length from scored-file *bodies*. ``text_for(n)``
        returns the text for length n (an adapter reads the file and supplies it).
        ``min_score``/``max_score`` apply the same band filter the rest of the system
        uses (``max_score`` ``None`` == a plain acceptance-bar floor), so every entry a
        fill can use already clears the bar. A length that ends up empty after
        filtering is kept as an empty bucket (its slots become unfillable)."""
        buckets: dict[int, Lexicon | _EmptyLexicon] = {}
        for n in sorted(set(lengths)):
            lex = Lexicon.from_scored_text(text_for(n), length=n).filtered(min_score, max_score)
            buckets[n] = lex if len(lex) else _EmptyLexicon(n)
        return cls(buckets)
