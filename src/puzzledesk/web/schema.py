"""The wire schema: the JSON an HTTP client sends/receives, parsed into (and rendered
from) the canonical ``app`` types.

Two directions, both kept *separate* from the app types they bridge (D15):

  * **request** -- :class:`PuzzleRequest` (a discriminated union of layout bodies)
    validates an incoming JSON body and ``to_spec()``\\ s it into a
    :class:`~puzzledesk.app.spec.PuzzleSpec`. The illegal knob combinations the app
    union already makes unrepresentable stay unrepresentable here: each layout body
    carries only *its* engine's knobs, discriminated on ``kind``.
  * **response** -- :class:`PuzzleView` renders a stored puzzle as the JSON a player
    consumes (grid + numbering + clued Across/Down), a *view* beside
    ``cli.present.playable``, built by :func:`puzzle_view`.

Note on the answer key: this view embeds answers (the same trust model as the static
``site/`` player, which checks in the browser). A key-free *solving* view -- the mirror
of :class:`~puzzledesk.app.solve.SolveView` -- is a Phase-2 concern, for when solves are
validated server-side and the client is no longer trusted with the key (roadmap).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from puzzledesk.app.clue import ClueStyle, Difficulty
from puzzledesk.app.repository import StoredPuzzle
from puzzledesk.app.spec import (
    CappedLayout,
    CountLayout,
    FillSpec,
    FullSquare,
    GibbsLayout,
    GridSpec,
    LayoutStrategy,
    PuzzleSpec,
)

# --------------------------------------------------------------------------- request


class GridBody(BaseModel):
    """The shape + quality band + seed (maps to :class:`~puzzledesk.app.spec.GridSpec`)."""

    rows: int = 5
    cols: int = 5
    min_score: float = 75.0
    max_score: float | None = None
    seed: int = 0

    def to_grid(self) -> GridSpec:
        return GridSpec(
            rows=self.rows,
            cols=self.cols,
            min_score=self.min_score,
            max_score=self.max_score,
            seed=self.seed,
        )


class FullSquareBody(BaseModel):
    """The fully-checked square (no black cells); complete search."""

    kind: Literal["full_square"] = "full_square"

    def to_strategy(self) -> LayoutStrategy:
        return FullSquare()


class CountBody(BaseModel):
    """A blocked layout from an exact black-cell count (D13); complete search."""

    kind: Literal["count"] = "count"
    num_black: int = 4
    symmetric: bool = True
    min_len: int = 3

    def to_strategy(self) -> LayoutStrategy:
        return CountLayout(num_black=self.num_black, symmetric=self.symmetric, min_len=self.min_len)


class CappedBody(BaseModel):
    """A blocked layout capping every entry's length (D24); budgeted search."""

    kind: Literal["capped"] = "capped"
    max_len: int
    num_black: int | None = None
    max_black: int | None = None
    symmetric: bool = True
    min_len: int = 3
    max_patterns: int | None = None

    def to_strategy(self) -> LayoutStrategy:
        return CappedLayout(
            max_len=self.max_len,
            num_black=self.num_black,
            max_black=self.max_black,
            symmetric=self.symmetric,
            min_len=self.min_len,
            max_patterns=self.max_patterns,
        )


class GibbsBody(BaseModel):
    """A blocked layout sampled from the Gibbs energy field (D27); sampler."""

    kind: Literal["gibbs"] = "gibbs"
    max_len: int
    num_black: int | None = None
    symmetric: bool = True
    min_len: int = 3
    max_layouts: int = 40

    def to_strategy(self) -> LayoutStrategy:
        return GibbsLayout(
            max_len=self.max_len,
            num_black=self.num_black,
            symmetric=self.symmetric,
            min_len=self.min_len,
            max_layouts=self.max_layouts,
        )


#: A tagged union over ``kind`` -- the wire mirror of ``app.spec.LayoutStrategy``, so a
#: body carries only its own engine's knobs and Pydantic rejects a mismatched shape.
LayoutBody = Annotated[
    FullSquareBody | CountBody | CappedBody | GibbsBody, Field(discriminator="kind")
]


class FillBody(BaseModel):
    """Fill-selection knobs (difficulty targeting, D23)."""

    min_hard_gets: int = 0
    gimme: float = 80.0

    def to_fill(self) -> FillSpec:
        return FillSpec(min_hard_gets=self.min_hard_gets, gimme=self.gimme)


class ClueBody(BaseModel):
    """Clue style: the Mon..Sat difficulty (1..6) plus free-form instructions."""

    difficulty: int = Field(default=int(Difficulty.WEDNESDAY), ge=1, le=6)
    instructions: str = ""

    def to_style(self) -> ClueStyle:
        return ClueStyle(difficulty=Difficulty(self.difficulty), instructions=self.instructions)


class PuzzleRequest(BaseModel):
    """The whole-puzzle request body -- the wire mirror of
    :class:`~puzzledesk.app.spec.PuzzleSpec`, which :meth:`to_spec` builds."""

    grid: GridBody = Field(default_factory=GridBody)
    layout: LayoutBody = Field(default_factory=CountBody)
    fill: FillBody = Field(default_factory=FillBody)
    clue: ClueBody = Field(default_factory=ClueBody)

    def to_spec(self) -> PuzzleSpec:
        return PuzzleSpec(
            grid=self.grid.to_grid(),
            layout=self.layout.to_strategy(),
            fill=self.fill.to_fill(),
            clue=self.clue.to_style(),
        )


# -------------------------------------------------------------------------- response


class EntryView(BaseModel):
    """One clued entry in the response (an Across or a Down)."""

    num: int
    clue: str
    answer: str
    length: int
    cells: list[tuple[int, int]]


class PuzzleView(BaseModel):
    """A stored puzzle as the JSON a player consumes: the grid, its numbering, and the
    clued Across/Down lists. Answers are embedded (see the module note)."""

    id: str
    rows: int
    cols: int
    difficulty: str
    cells: list[list[str | None]]
    numbering: dict[str, int]
    across: list[EntryView]
    down: list[EntryView]
    unclued: list[str]


def puzzle_view(stored: StoredPuzzle) -> PuzzleView:
    """Render a :class:`~puzzledesk.app.repository.StoredPuzzle` as a
    :class:`PuzzleView`. Everything semantic is *derived* from the grid geometry --
    runs, numbering -- mirroring ``cli.present.playable`` (invariant: numbering is
    derived on demand, never stored)."""
    puzzle = stored.puzzle
    grid = puzzle.grid
    numbering = grid.numbering()

    def entries(kind: str) -> list[EntryView]:
        ts = sorted((t for t in grid.runs() if t.kind == kind), key=lambda t: numbering[t.cells[0]])
        out: list[EntryView] = []
        for t in ts:
            clue = puzzle.clues.get(t.id)
            out.append(
                EntryView(
                    num=numbering[t.cells[0]],
                    clue=clue.text if clue is not None else "",
                    answer=t.answer.upper(),
                    length=len(t.cells),
                    cells=[(r, c) for (r, c) in t.cells],
                )
            )
        return out

    cells = [[None if ch is None else ch.upper() for ch in row] for row in grid.cells]
    return PuzzleView(
        id=stored.id,
        rows=grid.rows,
        cols=grid.cols,
        difficulty=stored.spec.clue.difficulty.name.title(),
        cells=cells,
        numbering={f"{r},{c}": n for (r, c), n in numbering.items()},
        across=entries("A"),
        down=entries("D"),
        unclued=[f"{cell[0]},{cell[1]},{kind}" for (cell, kind) in puzzle.unclued],
    )
