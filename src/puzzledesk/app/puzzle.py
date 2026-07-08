"""The puzzle in its canonical, space-first form -- what the cluing context speaks.

A filled crossword *is* a grid of cells, each holding a letter (a string; length
>1 is a rebus) or nothing (a black square). That is the whole truth; everything
semantic -- the across/down words, the crossing graph, the clue numbering -- is a
*derivation* of the geometry, computed on demand, never stored. This mirrors how a
Sudoku is a 9x9 grid, not a pre-materialised ``{rows, columns, boxes}`` object.

Two design rules this module encodes (see docs/decisions.md D15):

  * **Send the canonical aggregate; derive views at the point of use.** ``runs()``
    and ``crossings()`` are pure functions over the grid, not fields. A provider
    uses whichever lens it wants and ignores the rest.
  * **Model only where an external contract forces it.** The one structure beyond
    the grid is :class:`Target` -- because the *output* of cluing is per-word, not
    per-cell, so a word-level identity is unavoidable. Its identity is spatial
    (start cell + kind), still a derivation, not a re-architected entity.

:class:`FilledGrid` is representation-agnostic: both core grid models render into
it (:func:`filled_from_square`, :func:`filled_from_blocked`), so the clue port
never learns which model produced the fill -- honouring invariant 0 (two coexisting
grid models). That projection is the anti-corruption layer between core and the
cluing context.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core.blocked import BlockedGrid
from ..core.engines import fill
from ..core.square import DoubleSquare

Cell = tuple[int, int]
TargetId = tuple[Cell, str]


@dataclass(frozen=True, slots=True)
class Target:
    """Something to be clued: an ordered run of cells and the answer they spell.

    Entries are targets derived from the grid's runs (``kind`` ``"A"``/``"D"``); a
    meta is a target over highlighted cells (``kind`` ``"meta"``) -- so a
    puzzle-level meta clue needs no special channel, it is just another target.
    Identity is spatial: the start cell plus the kind.
    """

    cells: tuple[Cell, ...]
    answer: str
    kind: str  # "A" (across) | "D" (down) | "meta"

    @property
    def id(self) -> TargetId:
        return (self.cells[0], self.kind)


@dataclass(frozen=True, slots=True)
class Crossing:
    """Two targets that share a cell -- the interlock, derived from the geometry.
    The shared letter is ``a.answer``/``b.answer`` at ``cell``'s offset in each."""

    a: Target
    b: Target
    cell: Cell


@dataclass(frozen=True, slots=True)
class FilledGrid:
    """A filled crossword as cells + occupation: each cell a string (a letter, or
    several for a rebus) or ``None`` for a black square. The canonical aggregate;
    runs/crossings/numbering are derivations, never stored."""

    cells: tuple[tuple[str | None, ...], ...]

    @property
    def rows(self) -> int:
        return len(self.cells)

    @property
    def cols(self) -> int:
        return len(self.cells[0]) if self.cells else 0

    def _answer(self, cells: tuple[Cell, ...]) -> str:
        # cells are guaranteed non-black by the callers; the filter keeps mypy happy.
        return "".join(ch for (r, c) in cells if (ch := self.cells[r][c]) is not None)

    def runs(self, *, min_len: int = 2) -> tuple[Target, ...]:
        """Every maximal white run (across then down) of length >= ``min_len``, as
        the across/down entry-targets. ``min_len`` defaults to 2 (a single cell is
        not a word); our grids never carry sub-``min_len`` runs by construction."""
        out: list[Target] = []
        for r in range(self.rows):
            c = 0
            while c < self.cols:
                if self.cells[r][c] is None:
                    c += 1
                    continue
                seg = []
                while c < self.cols and self.cells[r][c] is not None:
                    seg.append((r, c))
                    c += 1
                if len(seg) >= min_len:
                    cells = tuple(seg)
                    out.append(Target(cells, self._answer(cells), "A"))
        for c in range(self.cols):
            r = 0
            while r < self.rows:
                if self.cells[r][c] is None:
                    r += 1
                    continue
                seg = []
                while r < self.rows and self.cells[r][c] is not None:
                    seg.append((r, c))
                    r += 1
                if len(seg) >= min_len:
                    cells = tuple(seg)
                    out.append(Target(cells, self._answer(cells), "D"))
        return tuple(out)

    def crossings(self) -> tuple[Crossing, ...]:
        """Every (across, down) pair sharing a cell -- the interlock, derived."""
        runs = self.runs()
        down_at: dict[Cell, Target] = {cell: t for t in runs if t.kind == "D" for cell in t.cells}
        out: list[Crossing] = []
        for across in (t for t in runs if t.kind == "A"):
            for cell in across.cells:
                down = down_at.get(cell)
                if down is not None:
                    out.append(Crossing(across, down, cell))
        return tuple(out)


def filled_from_square(sq: DoubleSquare, state: np.ndarray) -> FilledGrid:
    """Project a solved double word square into a FilledGrid (no black cells)."""
    grid = sq.grid(state)
    cells = tuple(tuple(chr(int(grid[r][c]) + 97) for c in range(sq.n)) for r in range(sq.n))
    return FilledGrid(cells)


def filled_from_blocked(g: BlockedGrid, assign: dict[int, str]) -> FilledGrid:
    """Project a filled blocked grid into a FilledGrid (black cells become None)."""
    letters = fill.letters_of(g, assign)
    cells = tuple(
        tuple(None if g.block[r][c] else letters.get((r, c)) for c in range(g.cols))
        for r in range(g.rows)
    )
    return FilledGrid(cells)
