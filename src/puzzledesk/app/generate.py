"""The grid-generation use-case: one service, one dispatched search, over every layout
strategy (D32).

This replaces the earlier ``BlockedGenerateService``'s four near-duplicate methods
(``fill_once`` / ``fill_capped_once`` / ``fill_capped_gibbs_once`` / ``fill_grid_once``,
each a flat bag of kwargs) with a single search dispatched on a :data:`LayoutStrategy`
value (:mod:`puzzledesk.app.spec`). The strategy *type* now carries which engine runs and
which of its knobs are legal; ``match`` + :func:`assert_never` make the two coexisting grid
models (invariant 0) -- and a new engine -- an exhaustiveness obligation rather than an
``if``-ladder in the caller.

Two public shapes come out of the one search:

  * :meth:`GenerateService.fill_grid` -> a model-agnostic :class:`FilledGrid` (the D15
    anti-corruption aggregate the cluing/solving contexts and the API speak). Handles
    *all* strategies, including :class:`FullSquare` -- so a square and a blocked grid flow
    through the same call.
  * :meth:`GenerateService.fill` -> a scored :class:`BlockedResult` for the blocked
    strategies (what the ``generate`` tool presents). A square's scored artifact is a
    ``MiniResult`` from :class:`~puzzledesk.app.mini.MiniService`, so ``fill`` rejects
    :class:`FullSquare`.

Injected as before: the length-bucketed word list via :class:`LexiconSource`, randomness
via :class:`RngFactory`. Completeness epistemics are unchanged and now *typed*
(:func:`layout_is_complete`): a ``None`` from a complete strategy is a UNSAT proof; from a
budgeted/sampled one it is budget exhaustion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

import numpy as np

from puzzledesk.app.ports import LexiconSource
from puzzledesk.app.puzzle import FilledGrid, filled_from_blocked, filled_from_square
from puzzledesk.app.results import BlockedResult, Entry
from puzzledesk.app.spec import (
    CappedLayout,
    CountLayout,
    FullSquare,
    GibbsLayout,
    GridSpec,
    LayoutStrategy,
)
from puzzledesk.core.blocked import BlockedGrid
from puzzledesk.core.engines import backtrack, fill, gibbs_layout, patterns
from puzzledesk.core.lexicon import MultiLexicon
from puzzledesk.core.rng import RngFactory
from puzzledesk.core.square import DoubleSquare

# Default black-cell density for a capped mini when the caller pins no count (D25).
# ~22% of the cells, as an upper bound; the white-biased search lands a little under it
# (measured ~16-22% on a 10x10), which reads like a real crossword. 22% leaves enough
# slack above the minimum feasible count to avoid the pathological backtracking a ceiling
# *at* the minimum triggers (D25); tighter is still available via an explicit max_black.
DEFAULT_BLACK_FRACTION = 0.22

# Cap the layout search per seed so a shape/ceiling that backtracks heavily (e.g. a big
# grid at a tight cap) bails and the seed loop moves on, instead of hanging (D25). Only
# on the *generation* path; the completeness proof (layout_exists) runs unbudgeted.
_LAYOUT_NODE_BUDGET = 300_000


def default_black_ceiling(rows: int, cols: int) -> int:
    """The default ``max_black`` when no count is pinned: ``DEFAULT_BLACK_FRACTION`` of
    the cells (at least 2, so even a tiny grid has a usable ceiling)."""
    return max(2, round(DEFAULT_BLACK_FRACTION * rows * cols))


@dataclass(frozen=True, slots=True)
class _SquareFill:
    """A solved fully-checked square: the ``DoubleSquare`` and its across-word state."""

    sq: DoubleSquare
    state: np.ndarray


@dataclass(frozen=True, slots=True)
class _BlockedFill:
    """A filled blocked grid: the length-bucketed lexicon (for scoring), the layout, and
    the slot->word assignment."""

    mlex: MultiLexicon
    grid: BlockedGrid
    assign: dict[int, str]


_Fill = _SquareFill | _BlockedFill


class GenerateService:
    """Generate one grid for any layout strategy: dispatch the search on the strategy,
    then project the result into whichever view the caller needs."""

    def __init__(
        self, lexicon: LexiconSource, rng_factory: RngFactory, *, list_name: str = "cw"
    ) -> None:
        self._lexicon = lexicon
        self._rng = rng_factory
        self._list_name = list_name

    def fill_grid(self, grid: GridSpec, layout: LayoutStrategy) -> FilledGrid | None:
        """Generate a grid and project it into a model-agnostic :class:`FilledGrid` -- the
        aggregate the cluing/solving contexts and the API speak. Handles every strategy,
        square or blocked. ``None`` when nothing fills; whether that is a proof or budget
        exhaustion is the strategy's :func:`~puzzledesk.app.spec.layout_is_complete` tag."""
        found = self._search(grid, layout)
        if found is None:
            return None
        if isinstance(found, _SquareFill):
            return filled_from_square(found.sq, found.state)
        return filled_from_blocked(found.grid, found.assign)

    def fill(self, grid: GridSpec, layout: LayoutStrategy) -> BlockedResult | None:
        """Generate a *blocked* grid and shape it into a scored :class:`BlockedResult`
        (what the ``generate`` tool presents). A :class:`FullSquare` has no blocked result
        -- its scored artifact is a ``MiniResult`` from ``MiniService`` -- so it is
        rejected here rather than silently mis-shaped."""
        found = self._search(grid, layout)
        if found is None:
            return None
        if isinstance(found, _SquareFill):
            raise ValueError("fill() produces a blocked result; use MiniService for FullSquare")
        return result_of(found.grid, found.mlex, found.assign)

    def layout_exists(self, grid: GridSpec, layout: LayoutStrategy) -> bool:
        """Does any legal layout exist for this shape + strategy at all -- a property of
        the geometry, independent of the words? For the blocked strategies this runs the
        layout search *unbudgeted*, so an empty answer is the genuine existence theorem
        (e.g. an odd black count on a symmetric even grid). A :class:`FullSquare` has the
        trivial empty layout, so existence is a fill question, not a layout one -> True."""
        match layout:
            case FullSquare():
                return True
            case CountLayout():
                layouts = patterns.gen_patterns(
                    grid.rows,
                    grid.cols,
                    layout.num_black,
                    rng=self._rng.create(0),
                    min_len=layout.min_len,
                    symmetric=layout.symmetric,
                )
                return next(layouts, None) is not None
            case CappedLayout():
                layouts = patterns.gen_capped(
                    grid.rows,
                    grid.cols,
                    rng=self._rng.create(0),
                    cap=patterns.CapSpec(
                        min_len=layout.min_len,
                        max_len=layout.max_len,
                        symmetric=layout.symmetric,
                        num_black=layout.num_black,
                        max_black=layout.max_black,
                    ),
                )
                return next(layouts, None) is not None
            case GibbsLayout():
                # The field is a sampler; its existence theorem is the complete search's.
                layouts = patterns.gen_capped(
                    grid.rows,
                    grid.cols,
                    rng=self._rng.create(0),
                    cap=patterns.CapSpec(
                        min_len=layout.min_len,
                        max_len=layout.max_len,
                        symmetric=layout.symmetric,
                        num_black=layout.num_black,
                    ),
                )
                return next(layouts, None) is not None
        assert_never(layout)

    # -- the one dispatched search -------------------------------------------------

    def _search(self, grid: GridSpec, layout: LayoutStrategy) -> _Fill | None:
        """Run the layout+fill search for ``layout``, returning the raw solved artifact
        (a square state or a blocked assignment) so each public method shapes its own
        view. The single point where the strategy chooses the engine."""
        match layout:
            case FullSquare():
                return self._square(grid)
            case CountLayout():
                return self._count(grid, layout)
            case CappedLayout():
                return self._capped(grid, layout)
            case GibbsLayout():
                return self._gibbs(grid, layout)
        assert_never(layout)

    def _square(self, grid: GridSpec) -> _SquareFill | None:
        if grid.rows != grid.cols:
            raise ValueError(
                f"a fully-checked square needs rows == cols, got {grid.rows}x{grid.cols}"
            )
        lex = self._lexicon.load(
            self._list_name, grid.rows, min_score=grid.min_score, max_score=grid.max_score
        )
        sq = DoubleSquare(lex)
        state = backtrack.solve(sq, rng=self._rng.create(grid.seed), distinct=True)
        return None if state is None else _SquareFill(sq, state)

    def _count(self, grid: GridSpec, layout: CountLayout) -> _BlockedFill | None:
        lengths = range(layout.min_len, max(grid.rows, grid.cols) + 1)
        mlex = self._lexicon.load_multi(
            self._list_name, lengths, min_score=grid.min_score, max_score=grid.max_score
        )
        found = patterns.fill_by_count(
            grid.rows,
            grid.cols,
            layout.num_black,
            mlex,
            rng_factory=self._rng,
            seed=grid.seed,
            symmetric=layout.symmetric,
            min_len=layout.min_len,
            distinct=True,
        )
        return None if found is None else _BlockedFill(mlex, *found)

    def _capped(self, grid: GridSpec, layout: CappedLayout) -> _BlockedFill | None:
        num_black, max_black = layout.num_black, layout.max_black
        if num_black is None and max_black is None:
            max_black = default_black_ceiling(grid.rows, grid.cols)
        mlex = self._lexicon.load_multi(
            self._list_name, range(layout.min_len, layout.max_len + 1), min_score=grid.min_score
        )
        found = patterns.fill_capped(
            grid.rows,
            grid.cols,
            mlex,
            rng_factory=self._rng,
            cap=patterns.CapSpec(
                max_len=layout.max_len,
                min_len=layout.min_len,
                symmetric=layout.symmetric,
                num_black=num_black,
                max_black=max_black,
            ),
            seed=grid.seed,
            distinct=True,
            budget=patterns.SearchBudget(
                layout_nodes=_LAYOUT_NODE_BUDGET, max_patterns=layout.max_patterns
            ),
        )
        return None if found is None else _BlockedFill(mlex, *found)

    def _gibbs(self, grid: GridSpec, layout: GibbsLayout) -> _BlockedFill | None:
        target_black = layout.num_black if layout.num_black and layout.num_black > 0 else None
        if target_black is None:
            params = gibbs_layout.FieldParams.from_fraction(
                grid.rows,
                grid.cols,
                black_fraction=DEFAULT_BLACK_FRACTION,
                min_len=layout.min_len,
                max_len=layout.max_len,
            )
        else:
            params = gibbs_layout.FieldParams(
                min_len=layout.min_len, max_len=layout.max_len, target_black=target_black
            )
        mlex = self._lexicon.load_multi(
            self._list_name, range(layout.min_len, layout.max_len + 1), min_score=grid.min_score
        )
        found = gibbs_layout.fill_gibbs(
            grid.rows,
            grid.cols,
            mlex,
            rng_factory=self._rng,
            params=params,
            seed=grid.seed,
            symmetric=layout.symmetric,
            distinct=True,
            budget=gibbs_layout.SampleBudget(max_layouts=layout.max_layouts),
        )
        return None if found is None else _BlockedFill(mlex, *found)


def result_of(g: BlockedGrid, mlex: MultiLexicon, assign: dict[int, str]) -> BlockedResult:
    """Shape a filled blocked grid into a :class:`BlockedResult`. Public so the blocked
    benchmark CLIs, which drive ``fill.solve`` directly, present through the same path as
    the service."""
    grid = g.render(fill.letters_of(g, assign))

    def entries(direction: str) -> list[Entry]:
        out = [
            Entry(s.number, direction, assign[s.id], mlex.get(s.length).score_map[assign[s.id]])
            for s in g.slots
            if s.direction == direction
        ]
        return sorted(out, key=lambda e: e.number)

    return BlockedResult(grid=grid, across=entries("A"), down=entries("D"))
