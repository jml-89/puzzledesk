"""Presenters: turn service results into lines on a ``Writer``.

The formatting that used to live in each script's ``render``/``show`` function,
gathered in one place and driven by the structured results the services return.
Pure string-building plus ``writer.line`` calls -- no generation, no numpy.
"""

from __future__ import annotations

from ..app.cluing import CluedPuzzle
from ..app.ports import Writer
from ..app.puzzle import FilledGrid
from ..app.results import BlockedResult, MiniBatch, MiniResult


def mini_batch(batch: MiniBatch, writer: Writer) -> None:
    """Render a batch of minis exactly as ``scripts/mini.py`` did."""
    writer.line(
        f"{batch.n}x{batch.n} minis, every word score >= {batch.min_score:.0f} "
        f"(from {batch.eligible} eligible words)"
    )
    writer.line()
    if not batch.results:
        writer.line("no grid at this bar (try a lower min_score)")
        return
    for r in batch.results:
        _mini(r, writer)


def _mini(r: MiniResult, writer: Writer) -> None:
    for a in r.across:
        writer.line("  " + " ".join(ch.upper() for ch in a.word))
    writer.line("  across: " + ", ".join(f"{a.word}({a.score:.0f})" for a in r.across))
    writer.line("  down:   " + ", ".join(f"{d.word}({d.score:.0f})" for d in r.down))
    writer.line(f"  weakest word: {r.weakest.word} ({r.weakest.score:.0f})")
    writer.line()


def blocked_result(res: BlockedResult, writer: Writer) -> None:
    """Render a filled blocked grid: the letter grid, then the across/down entries
    with scores -- the shared format of ``blackcells.py`` and ``generate.py``."""
    writer.line(res.grid)
    across = "  ".join(f"{e.number}A {e.word}({e.score:.0f})" for e in res.across)
    down = "  ".join(f"{e.number}D {e.word}({e.score:.0f})" for e in res.down)
    writer.line(f"  across: {across}")
    writer.line(f"  down:   {down}")


# --- Playable puzzle: the solver-facing plain-text view --------------------------
#
# The presenter the QA round wanted: a blank numbered grid plus numbered clue lists,
# i.e. a puzzle you can *solve* rather than the answer key the other presenters emit.
# Pure ASCII (``+ - | #`` and digits) so it renders identically in any terminal or
# pasted into any text box; box-drawing glyphs are deliberately avoided. All the
# structure -- numbering, entry lengths, across/down split -- is derived from the
# grid geometry (``FilledGrid``), never stored (D15).

_UNCLUED = "[no clue available]"


def playable(puzzle: CluedPuzzle, writer: Writer) -> None:
    """Render a clued puzzle for solving: the blank numbered grid, then the Across
    and Down clue lists. Answers are never shown -- use :func:`solution` for those."""
    grid = puzzle.grid
    numbering = grid.numbering()
    for line in _grid_lines(grid, numbering):
        writer.line(line)
    writer.line()
    _clue_block("Across", "A", puzzle, numbering, writer)
    writer.line()
    _clue_block("Down", "D", puzzle, numbering, writer)


def solution(grid: FilledGrid, writer: Writer) -> None:
    """Render the answer key: the filled letter grid (uppercase, ``#`` for black).
    The reveal companion to :func:`playable`, for QA and for ``--reveal``."""
    for row in grid.cells:
        writer.line(" ".join(cell.upper() if cell is not None else "#" for cell in row))


def _grid_lines(grid: FilledGrid, numbering: dict[tuple[int, int], int]) -> list[str]:
    """The blank grid as ASCII box rows: black cells filled with ``#``, white cells
    blank but carrying their clue number (if any) in the corner. Cell width grows to
    fit the largest number, so bigger grids stay aligned."""
    width = max(2, len(str(max(numbering.values(), default=0))))
    border = "+" + "+".join("-" * width for _ in range(grid.cols)) + "+"
    lines = [border]
    for r in range(grid.rows):
        cells = []
        for c in range(grid.cols):
            if grid.cells[r][c] is None:
                cells.append("#" * width)
            elif (n := numbering.get((r, c))) is not None:
                cells.append(str(n).ljust(width))
            else:
                cells.append(" " * width)
        lines.append("|" + "|".join(cells) + "|")
        lines.append(border)
    return lines


def _clue_block(
    title: str,
    kind: str,
    puzzle: CluedPuzzle,
    numbering: dict[tuple[int, int], int],
    writer: Writer,
) -> None:
    """One clue list ("Across"/"Down"): numbered entries in grid order, each with its
    clue text and answer length -- ``(no clue found)`` reported honestly if unclued."""
    writer.line(title)
    entries = sorted(
        (t for t in puzzle.grid.runs() if t.kind == kind),
        key=lambda t: numbering[t.cells[0]],
    )
    for t in entries:
        clue = puzzle.clues.get(t.id)
        text = clue.text if clue is not None else _UNCLUED
        writer.line(f"  {numbering[t.cells[0]]}. {text} ({len(t.cells)})")
