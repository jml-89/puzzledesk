"""Exhaustive enumeration of double word squares -- ground truth for testing.

Tractable only for tiny orders (N=2, and N=3 with a filtered list). We fill
rows top to bottom and prune any partial grid whose columns are no longer live
prefixes of some column word. This is the classic trie-style pruning; here we
just use a prefix set built from the column lexicon.
"""

from __future__ import annotations

from puzzledesk.core.lexicon import Lexicon


def _prefix_set(words: list[str]) -> set[str]:
    pref: set[str] = set()
    for w in words:
        for k in range(len(w) + 1):
            pref.add(w[:k])
    return pref


def enumerate_squares(
    rows: Lexicon, cols: Lexicon | None = None, limit: int | None = None
) -> list[tuple[str, ...]]:
    """Yield every valid double word square as a tuple of N row strings."""
    cols = cols if cols is not None else rows
    n = rows.n
    col_prefixes = _prefix_set(cols.words)
    col_words = cols.wordset
    results: list[tuple[str, ...]] = []

    def columns_live(partial: list[str]) -> bool:
        # Every column so far must be a prefix of some column word.
        return all("".join(row[j] for row in partial) in col_prefixes for j in range(n))

    def recurse(partial: list[str]) -> None:
        if limit is not None and len(results) >= limit:
            return
        if len(partial) == n:
            if all("".join(row[j] for row in partial) in col_words for j in range(n)):
                results.append(tuple(partial))
            return
        for w in rows.words:
            partial.append(w)
            if columns_live(partial):
                recurse(partial)
            partial.pop()

    recurse([])
    return results
