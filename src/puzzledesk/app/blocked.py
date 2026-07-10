"""The blocked-mini use-case: generate an American-style grid from a black-cell
*count*, then fill it above a quality bar.

Composes the two complete searches (``patterns.gen_patterns`` for a legal layout,
``fill.solve`` for a distinct fill) via ``patterns.fill_by_count``. Because both
are complete, a None fill for a shape at which legal layouts *do* exist is a real
"unfillable at this bar" theorem, distinct from "no legal layout exists at all" --
so the service exposes both questions and lets the presenter word them.

Injected: the length-bucketed word list via :class:`LexiconSource`, randomness via
:class:`RngFactory`.
"""

from __future__ import annotations

from puzzledesk.app.ports import LexiconSource
from puzzledesk.app.puzzle import FilledGrid, filled_from_blocked
from puzzledesk.app.results import BlockedResult, Entry
from puzzledesk.core.blocked import BlockedGrid
from puzzledesk.core.engines import fill, gibbs_layout, patterns
from puzzledesk.core.lexicon import MultiLexicon
from puzzledesk.core.rng import RngFactory

# Default black-cell density for a capped mini when the caller pins no count (D25).
# ~22% of the cells, as an upper bound; the white-biased search lands a little under it
# (measured ~16-22% on a 10x10), which reads like a real crossword. 22% leaves enough
# slack above the minimum feasible count to avoid the pathological backtracking a ceiling
# *at* the minimum triggers (D25); tighter is still available via an explicit max_black.
DEFAULT_BLACK_FRACTION = 0.22

# Cap the layout search per seed so a shape/ceiling that backtracks heavily (e.g. a big
# grid at a tight cap) bails and the seed loop moves on, instead of hanging (D25). Only
# on the *generation* path; the completeness proof (capped_layout_exists) runs unbudgeted.
_LAYOUT_NODE_BUDGET = 300_000


def default_black_ceiling(rows: int, cols: int) -> int:
    """The default ``max_black`` when no count is pinned: ``DEFAULT_BLACK_FRACTION`` of
    the cells (at least 2, so even a tiny grid has a usable ceiling)."""
    return max(2, round(DEFAULT_BLACK_FRACTION * rows * cols))


class BlockedGenerateService:
    """Generate blocked minis: search legal layouts of a given black-cell count
    and fill the first that solves above the bar."""

    def __init__(
        self, lexicon: LexiconSource, rng_factory: RngFactory, *, list_name: str = "cw"
    ) -> None:
        self._lexicon = lexicon
        self._rng = rng_factory
        self._list_name = list_name

    def layout_exists(
        self, rows: int, cols: int, num_black: int, *, symmetric: bool = True, min_len: int = 3
    ) -> bool:
        """Does any legal (checked, connected, symmetric?) layout with this many
        blacks exist at all -- a property of the shape, independent of the words?"""
        layouts = patterns.gen_patterns(
            rows, cols, num_black, rng=self._rng.create(0), min_len=min_len, symmetric=symmetric
        )
        return next(layouts, None) is not None

    def fill_once(
        self,
        rows: int,
        cols: int,
        num_black: int,
        *,
        min_score: float,
        max_score: float | None = None,
        seed: int = 0,
        symmetric: bool = True,
        min_len: int = 3,
    ) -> BlockedResult | None:
        """One layout+fill attempt for ``seed``: the first legal layout that admits
        a distinct fill in the band, or None (complete, so None settles it)."""
        found = self._fill(
            rows,
            cols,
            num_black,
            min_score=min_score,
            max_score=max_score,
            seed=seed,
            symmetric=symmetric,
            min_len=min_len,
        )
        if found is None:
            return None
        mlex, (grid, assign) = found
        return result_of(grid, mlex, assign)

    def fill_capped_once(
        self,
        rows: int,
        cols: int,
        *,
        max_len: int,
        min_score: float,
        seed: int = 0,
        symmetric: bool = True,
        min_len: int = 3,
        num_black: int | None = None,
        max_black: int | None = None,
        max_patterns: int | None = None,
    ) -> BlockedResult | None:
        """A *length-capped* mini: every entry has length in ``[min_len, max_len]``,
        so a grid larger than the word data can fill (e.g. 10x10 from the 2..5 lists).

        Searches :func:`patterns.gen_capped` layouts (cap-driven, count derived) and
        fills the first that solves above the bar. Density (D25): ``num_black`` pins the
        count exactly, ``max_black`` bounds it above; with **neither** given the search
        defaults to a sensible black ceiling (:data:`DEFAULT_BLACK_FRACTION` of the
        cells) so the free path yields clean, real-crossword-like grids instead of the
        over-black uniform search. Because the cap keeps entries within the loaded
        lengths (``range(min_len, max_len + 1)``), no word list beyond 5 is needed. The
        layout search here always runs under a node budget (and ``max_patterns`` may cap
        the attempts), so a ``None`` is budget exhaustion, **never** a UNSAT theorem (the
        capped layout space is astronomically large at 10x10); the unbudgeted existence
        proof is :meth:`capped_layout_exists`."""
        if num_black is None and max_black is None:
            max_black = default_black_ceiling(rows, cols)
        mlex = self._lexicon.load_multi(
            self._list_name, range(min_len, max_len + 1), min_score=min_score
        )
        found = patterns.fill_capped(
            rows,
            cols,
            mlex,
            rng_factory=self._rng,
            max_len=max_len,
            seed=seed,
            min_len=min_len,
            symmetric=symmetric,
            distinct=True,
            num_black=num_black,
            max_black=max_black,
            layout_node_budget=_LAYOUT_NODE_BUDGET,
            max_patterns=max_patterns,
        )
        if found is None:
            return None
        grid, assign = found
        return result_of(grid, mlex, assign)

    def fill_capped_gibbs_once(
        self,
        rows: int,
        cols: int,
        *,
        max_len: int,
        min_score: float,
        seed: int = 0,
        symmetric: bool = True,
        min_len: int = 3,
        num_black: int | None = None,
        max_layouts: int = 40,
    ) -> BlockedResult | None:
        """A length-capped mini whose *layout* is drawn from the Gibbs energy field
        (D27) instead of the complete cap-driven search -- the aesthetic-controlled path.

        Same output as :meth:`fill_capped_once` (a filled ``BlockedResult``); only the
        layout source differs. The field gives explicit, tunable control over density,
        spread, and the no-2x2-black-block rule -- properties ``gen_capped``'s heuristic
        gets only emergently (and which it can violate) -- at the cost of speed and, being
        a sampler, *completeness*: a ``None`` here is budget exhaustion (no layout sampled
        that filled within ``max_layouts``), **never** a UNSAT theorem. Density is set by
        ``num_black`` (an exact-count spring) or, unset, by :data:`DEFAULT_BLACK_FRACTION`
        of the cells. Entries stay within ``[min_len, max_len]``, so no word list beyond
        ``max_len`` is needed."""
        target_black = num_black if num_black and num_black > 0 else None
        black_fraction = DEFAULT_BLACK_FRACTION if target_black is None else 0.0
        mlex = self._lexicon.load_multi(
            self._list_name, range(min_len, max_len + 1), min_score=min_score
        )
        found = gibbs_layout.fill_gibbs(
            rows,
            cols,
            mlex,
            rng_factory=self._rng,
            max_len=max_len,
            seed=seed,
            min_len=min_len,
            symmetric=symmetric,
            distinct=True,
            black_fraction=black_fraction,
            target_black=target_black,
            max_layouts=max_layouts,
        )
        if found is None:
            return None
        grid, assign = found
        return result_of(grid, mlex, assign)

    def capped_layout_exists(
        self,
        rows: int,
        cols: int,
        *,
        max_len: int,
        symmetric: bool = True,
        min_len: int = 3,
        num_black: int | None = None,
        max_black: int | None = None,
    ) -> bool:
        """Does any legal length-capped layout exist at all -- a property of the shape,
        the cap, and any count bound, independent of the words?"""
        layouts = patterns.gen_capped(
            rows,
            cols,
            rng=self._rng.create(0),
            min_len=min_len,
            max_len=max_len,
            symmetric=symmetric,
            num_black=num_black,
            max_black=max_black,
        )
        return next(layouts, None) is not None

    def fill_grid_once(
        self,
        rows: int,
        cols: int,
        num_black: int,
        *,
        min_score: float,
        max_score: float | None = None,
        seed: int = 0,
        symmetric: bool = True,
        min_len: int = 3,
    ) -> FilledGrid | None:
        """Same search as :meth:`fill_once`, projected into the model-agnostic
        :class:`~puzzledesk.app.puzzle.FilledGrid` the cluing context speaks -- the
        shape the puzzle service hands to :class:`~puzzledesk.app.cluing.ClueService`.
        None (unfillable in the band) settles it, exactly as ``fill_once``'s does."""
        found = self._fill(
            rows,
            cols,
            num_black,
            min_score=min_score,
            max_score=max_score,
            seed=seed,
            symmetric=symmetric,
            min_len=min_len,
        )
        if found is None:
            return None
        _, (grid, assign) = found
        return filled_from_blocked(grid, assign)

    def _fill(
        self,
        rows: int,
        cols: int,
        num_black: int,
        *,
        min_score: float,
        max_score: float | None,
        seed: int,
        symmetric: bool,
        min_len: int,
    ) -> tuple[MultiLexicon, tuple[BlockedGrid, dict[int, str]]] | None:
        """The shared layout+fill search behind both ``fill_once`` (which wants the
        scored result) and ``fill_grid_once`` (which wants the geometry). Returns the
        lexicon alongside the raw ``(grid, assign)`` so each caller shapes its own
        output; None when nothing fills in the band. A two-sided band ``[min, max]`` is
        the difficulty knob (D21): drawing from an obscure band makes the fill genuinely
        harder, so the clues alone become insufficient and the grid must carry the solve
        (D24) -- and the search stays complete, so None is still a real UNSAT theorem."""
        mlex = self._multi(rows, cols, min_score, max_score, min_len)
        found = patterns.fill_by_count(
            rows,
            cols,
            num_black,
            mlex,
            rng_factory=self._rng,
            seed=seed,
            symmetric=symmetric,
            min_len=min_len,
            distinct=True,
        )
        return None if found is None else (mlex, found)

    def _multi(
        self, rows: int, cols: int, min_score: float, max_score: float | None, min_len: int
    ) -> MultiLexicon:
        lengths = range(min_len, max(rows, cols) + 1)
        return self._lexicon.load_multi(
            self._list_name, lengths, min_score=min_score, max_score=max_score
        )


def result_of(g: BlockedGrid, mlex: MultiLexicon, assign: dict[int, str]) -> BlockedResult:
    """Shape a filled blocked grid into a :class:`BlockedResult`. Public so the
    blocked benchmark CLIs, which drive ``fill.solve`` directly, present through
    the same path as the service."""
    grid = g.render(fill.letters_of(g, assign))

    def entries(direction: str) -> list[Entry]:
        out = [
            Entry(s.number, direction, assign[s.id], mlex.get(s.length).score_map[assign[s.id]])
            for s in g.slots
            if s.direction == direction
        ]
        return sorted(out, key=lambda e: e.number)

    return BlockedResult(grid=grid, across=entries("A"), down=entries("D"))
