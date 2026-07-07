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
    def __init__(self, words: list[str]):
        if not words:
            raise ValueError("empty word list")
        self.n = len(words[0])
        if any(len(w) != self.n for w in words):
            raise ValueError("all words must share the same length")
        self.words = words
        self.wordset = set(words)
        # (M, N) letter-index matrix.
        self.letters = np.stack([encode(w) for w in words]).astype(np.uint8)

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
