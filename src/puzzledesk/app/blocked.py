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

from ..core.blocked import BlockedGrid
from ..core.engines import fill, patterns
from ..core.lexicon import MultiLexicon
from ..core.rng import RngFactory
from .ports import LexiconSource
from .results import BlockedResult, Entry


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
        seed: int = 0,
        symmetric: bool = True,
        min_len: int = 3,
    ) -> BlockedResult | None:
        """One layout+fill attempt for ``seed``: the first legal layout that admits
        a distinct fill above the bar, or None (complete, so None settles it)."""
        mlex = self._multi(rows, cols, min_score, min_len)
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
        if found is None:
            return None
        grid, assign = found
        return result_of(grid, mlex, assign)

    def _multi(self, rows: int, cols: int, min_score: float, min_len: int) -> MultiLexicon:
        lengths = range(min_len, max(rows, cols) + 1)
        return self._lexicon.load_multi(self._list_name, lengths, min_score=min_score)


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
