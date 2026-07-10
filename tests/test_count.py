"""Solution counting: how *large* the square's solution space is (D31).

Contracts, in the small-first / ground-truth style of ``test_ground_truth.py``:

* an exhaustive ``count`` equals distinct-filtered brute-force enumeration
  (the counting analogue of "solver output is a subset of ground truth");
* the ``exact`` bit is honest -- a ``limit`` hit reports ``exact=False`` (>= limit),
  an exhausted walk reports ``exact=True`` (a theorem).
"""

from __future__ import annotations

from puzzledesk.core.engines import backtrack
from puzzledesk.core.engines.bruteforce import enumerate_squares
from puzzledesk.core.lexicon import Lexicon
from puzzledesk.core.square import DoubleSquare

# Small lists that admit several distinct squares, so counting has something to
# count and forced-down pruning has branches to cut.
_LISTS = [
    ["ab", "cd", "ac", "bd"],
    ["aa", "ab", "ba", "bb"],
    ["cat", "car", "cot", "cab", "oar", "tar", "ace", "arc", "car"],
]


def _distinct_truth(sq: DoubleSquare) -> set[tuple[str, ...]]:
    """Brute-force distinct double squares (2N distinct words) -- ground truth."""
    out: set[tuple[str, ...]] = set()
    n = sq.n
    for rows in enumerate_squares(sq.rows):
        downs = tuple("".join(rows[r][c] for r in range(n)) for c in range(n))
        if len({*rows, *downs}) == 2 * n:
            out.add(rows)
    return out


def test_count_equals_distinct_ground_truth() -> None:
    for words in _LISTS:
        sq = DoubleSquare(Lexicon(list(dict.fromkeys(words))))
        res = backtrack.count(sq, distinct=True)
        assert res.exact
        assert res.n == len(_distinct_truth(sq))


def test_count_nondistinct_equals_full_enumeration() -> None:
    for words in _LISTS:
        sq = DoubleSquare(Lexicon(list(dict.fromkeys(words))))
        res = backtrack.count(sq, distinct=False)
        assert res.exact
        assert res.n == len(enumerate_squares(sq.rows))


def test_limit_is_honest_about_exactness() -> None:
    # {ab, cd, ac, bd} has more than one distinct square; capping at 1 must report
    # a non-exact ">= 1", not pretend the walk finished.
    sq = DoubleSquare(Lexicon(["ab", "cd", "ac", "bd"]))
    total = backtrack.count(sq, distinct=True)
    assert total.exact and total.n >= 2
    capped = backtrack.count(sq, distinct=True, limit=1)
    assert capped.n == 1
    assert not capped.exact  # "at least 1", the budget-exhaustion epistemics


def test_unsat_basin_counts_zero_exactly() -> None:
    # {ab, ba}: two valid squares, both the symmetric basin (across == down), so
    # ZERO distinct squares -- and the count proves it (exact 0), the counting twin
    # of test_invariants' "None is a real UNSAT proof".
    sq = DoubleSquare(Lexicon(["ab", "ba"]))
    distinct = backtrack.count(sq, distinct=True)
    assert distinct.n == 0 and distinct.exact
    both = backtrack.count(sq, distinct=False)
    assert both.n == 2 and both.exact
