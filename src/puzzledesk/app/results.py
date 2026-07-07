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
class MiniResult:
    """A single solved double word square: the across words, the induced down
    words, and the weakest of the 2N (the acceptance bottleneck)."""

    across: list[WordScore]
    down: list[WordScore]
    weakest: WordScore


@dataclass(frozen=True, slots=True)
class MiniBatch:
    """The output of one ``MiniService.generate`` call: the grids plus the header
    facts the caller reports (order, bar, how many words cleared the bar)."""

    n: int
    min_score: float
    eligible: int
    results: list[MiniResult]


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
