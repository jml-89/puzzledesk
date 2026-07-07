"""Lexicon: word storage plus the two lookup structures the sampler needs.

For a double word square of order N we only ever deal with words of a single
length N. We keep:

  * ``wordset``  - a Python set for O(1) "is this string a valid word" checks,
                   used to test whether an induced column is a real word.
  * ``letters``  - an (M, N) uint8 array of letter indices (0..25), one row per
                   word. This lets us answer per-position pattern queries with
                   vectorised NumPy instead of scanning strings.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

A = ord("a")


def encode(word: str) -> np.ndarray:
    """Map a lowercase word to an array of 0..25 letter indices."""
    return np.frombuffer(word.encode("ascii"), dtype=np.uint8) - A


def decode(codes: np.ndarray) -> str:
    """Inverse of :func:`encode`."""
    return bytes(int(c) + A for c in codes).decode("ascii")


class Lexicon:
    def __init__(self, words: list[str], scores: list[float] | None = None):
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
        self.scores = np.asarray(scores if scores is not None else [0.0] * len(words),
                                 dtype=np.float64)
        self.score_map = dict(zip(self.words, self.scores.tolist()))

    def __len__(self) -> int:
        return len(self.words)

    @classmethod
    def from_file(cls, path: str | Path, length: int | None = None) -> "Lexicon":
        words = []
        for line in Path(path).read_text().splitlines():
            w = line.strip().lower()
            if not w.isalpha():
                continue
            if length is not None and len(w) != length:
                continue
            words.append(w)
        # Dedupe, keep order stable for reproducibility.
        seen: set[str] = set()
        uniq = [w for w in words if not (w in seen or seen.add(w))]
        return cls(uniq)

    @classmethod
    def from_scored_file(cls, path: str | Path, length: int | None = None) -> "Lexicon":
        """Load a 'word score' per line file (see scripts/gen_scored.py)."""
        words, scores = [], []
        seen: set[str] = set()
        for line in Path(path).read_text().splitlines():
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

    def filtered(self, min_score: float) -> "Lexicon":
        """Sub-lexicon of words scoring at least ``min_score``. Filtering at the
        acceptance bar turns 'quality' into feasibility on a smaller list."""
        kept = [(w, s) for w, s in zip(self.words, self.scores.tolist()) if s >= min_score]
        return Lexicon([w for w, _ in kept], [s for _, s in kept])

    def is_word(self, s: str) -> bool:
        return s in self.wordset

    def allowed_at(self, pattern: list[int | None]) -> np.ndarray:
        """Given a length-N pattern with fixed letters and ``None`` blanks,
        return a 26-bool mask of letters that can fill the (single) blank so the
        whole string is a real word.

        ``pattern`` must have exactly one ``None``. Used to compute, for a given
        column, which letters at the free row make that column a valid word --
        the per-cell "marginal" that drives the local update.
        """
        blank = pattern.index(None)
        # Rows matching all the fixed positions.
        mask = np.ones(len(self.words), dtype=bool)
        for pos, val in enumerate(pattern):
            if val is None:
                continue
            mask &= self.letters[:, pos] == val
        allowed = np.zeros(26, dtype=bool)
        allowed[self.letters[mask, blank]] = True
        return allowed

    def allowed_and_scores_at(self, pattern: list[int | None]):
        """Like :meth:`allowed_at`, but also return a 26-array giving, for each
        letter that fills the blank, the score of the resulting word (0 where the
        letter is not allowed). Lets the sampler value the *induced* word, not
        just check its existence."""
        blank = pattern.index(None)
        mask = np.ones(len(self.words), dtype=bool)
        for pos, val in enumerate(pattern):
            if val is None:
                continue
            mask &= self.letters[:, pos] == val
        allowed = np.zeros(26, dtype=bool)
        colscore = np.zeros(26, dtype=np.float64)
        idx = np.nonzero(mask)[0]
        letters = self.letters[idx, blank]
        allowed[letters] = True
        colscore[letters] = self.scores[idx]  # column words are unique per letter
        return allowed, colscore

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
        have already fixed, and the candidates are the words that fit. Unlike
        :meth:`allowed_at` it allows *any* number of blanks, not exactly one.
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

    def __init__(self, n: int):
        self.n = n
        self.words: list[str] = []

    def __len__(self) -> int:
        return 0

    def matching(self, pattern) -> np.ndarray:
        return np.empty(0, dtype=np.intp)


class MultiLexicon:
    """Words bucketed by length -- what a blocked grid needs, since its slots no
    longer share one length. Holds a :class:`Lexicon` per length and routes
    pattern queries to the right bucket.

    A single-length ``Lexicon`` was enough while every row and column was one
    full-length word (the fully-checked square). Black cells cut the grid into
    slots of mixed length, so fill needs 2s, 3s, 4s, ... at once.
    """

    def __init__(self, by_length: dict):
        self.by_length = by_length

    def __contains__(self, length: int) -> bool:
        return length in self.by_length

    def get(self, length: int):
        if length not in self.by_length:
            return _EmptyLexicon(length)  # no list loaded => unfillable, not a crash
        return self.by_length[length]

    @classmethod
    def from_scored_files(cls, path_for, lengths, min_score: float = 0.0) -> "MultiLexicon":
        """Load one scored file per length. ``path_for(n)`` returns the path for
        length n (e.g. ``lambda n: DATA / f'cw_{n}.txt'``). ``min_score`` applies
        the same acceptance-bar filter the rest of the system uses, so every
        entry a fill can use already clears the bar. A length that ends up empty
        after filtering is kept as an empty bucket (its slots become unfillable)."""
        buckets: dict = {}
        for n in sorted(set(lengths)):
            lex = Lexicon.from_scored_file(path_for(n), length=n)
            kept = [(w, s) for w, s in zip(lex.words, lex.scores.tolist()) if s >= min_score]
            buckets[n] = Lexicon([w for w, _ in kept], [s for _, s in kept]) if kept else _EmptyLexicon(n)
        return cls(buckets)
