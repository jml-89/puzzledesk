"""Structured results the services return -- plain value objects, no I/O.

A service produces these; a ``cli`` presenter turns them into text. Keeping the
two apart means the generation logic is testable without capturing stdout, and
the output format can change without touching a service.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WordScore:
    """One word and its score, on that word's own list scale."""

    word: str
    score: float


@dataclass(frozen=True, slots=True)
class SolveDifficulty:
    """A grid's dynamic difficulty, from ``app.difficulty.solve_order`` (D21/D22).

    ``hard_gets`` is how many entries the easiest-first solver had to work obscure and
    still-open (0 == it fell to gimmes + forcing, a Monday); ``bottleneck`` is the
    hardest such entry (most fits to disambiguate). Both are read under ``gimme`` -- the
    clue-difficulty assumption, an input, not a measured label (D20 layer B)."""

    hard_gets: int
    bottleneck_word: str | None
    bottleneck_fits: int
    gimme: float


@dataclass(frozen=True, slots=True)
class MiniResult:
    """A single solved double word square: the across words, the induced down
    words, and the weakest of the 2N (the acceptance bottleneck). ``difficulty`` is
    attached only when generation targeted one (``min_hard_gets > 0``); else None."""

    across: list[WordScore]
    down: list[WordScore]
    weakest: WordScore
    difficulty: SolveDifficulty | None = None


@dataclass(frozen=True, slots=True)
class MiniBatch:
    """The output of one ``MiniService.generate`` call: the grids plus the header
    facts the caller reports (order, bar, how many words cleared the bar)."""

    n: int
    min_score: float
    eligible: int
    results: list[MiniResult]
    max_score: float | None = None  # set == a difficulty band [min, max] (D20)
    min_hard_gets: int = 0  # >0 == grids were selected to a difficulty target (D22)
    gimme: float = 80.0  # the clue-difficulty assumption the target was read under


@dataclass(frozen=True, slots=True)
class Entry:
    """One filled slot in a blocked grid: its clue number, direction and word."""

    number: int
    direction: str  # "A" (across) or "D" (down)
    word: str
    score: float


@dataclass(frozen=True, slots=True)
class BlockedResult:
    """A filled blocked grid: the rendered letter grid plus its entries. The grid
    string is produced by the pure core renderer, so it is data, not I/O."""

    grid: str
    across: list[Entry]
    down: list[Entry]
