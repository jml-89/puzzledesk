"""The end-to-end puzzle use-case: a :class:`PuzzleSpec` in, a *clued* puzzle out.

This is the composition the QA round found missing -- the seam between "the
generator emits a filled grid" and "a solver has a playable puzzle". It is pure
orchestration over two services already in this layer:

  * :class:`~puzzledesk.app.generate.GenerateService` searches a legal layout and fills
    it above the quality bar, for whichever :data:`~puzzledesk.app.spec.LayoutStrategy`
    the spec names -- a square or any blocked layout, uniformly, via ``fill_grid``;
  * :class:`~puzzledesk.app.cluing.ClueService` clues the filled grid through the
    :class:`~puzzledesk.app.clue.ClueProvider` port (the one soft, generative stage).

The service owns no I/O and no provider of its own -- it holds the two services and takes
one :class:`~puzzledesk.app.spec.PuzzleSpec` (grid + layout + fill + clue style). A
``None`` grid propagates as a ``None`` puzzle, so the completeness epistemics survive the
compose: whether "no puzzle" is a UNSAT proof or budget exhaustion is the spec's layout
tag (:func:`~puzzledesk.app.spec.layout_is_complete`), never a swallowed timeout.
"""

from __future__ import annotations

from puzzledesk.app.cluing import CluedPuzzle, ClueService
from puzzledesk.app.generate import GenerateService
from puzzledesk.app.spec import PuzzleSpec


class PuzzleService:
    """Generate a complete, clued puzzle: fill a grid per the spec, then clue it."""

    def __init__(self, generator: GenerateService, clue: ClueService) -> None:
        self._gen = generator
        self._clue = clue

    def generate(self, spec: PuzzleSpec) -> CluedPuzzle | None:
        """Fill ``spec.grid`` with the ``spec.layout`` strategy, then clue every entry in
        ``spec.clue``. A finite ``grid.max_score`` makes the fill an *obscurity band* -- a
        harder puzzle whose clues alone are insufficient, so the grid must carry the solve
        (D21/D26). ``None`` when no fill clears the band; the spec's layout tag says whether
        that is a UNSAT theorem or budget exhaustion. (``spec.fill`` -- difficulty targeting
        -- is reserved on the blocked path; the square batch path is ``MiniService``.)"""
        grid = self._gen.fill_grid(spec.grid, spec.layout)
        if grid is None:
            return None
        return self._clue.clue(grid, style=spec.clue)
