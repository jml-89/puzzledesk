"""The end-to-end puzzle use-case: a black-cell count in, a *clued* puzzle out.

This is the composition the QA round found missing -- the seam between "the
generator emits a filled grid + scores" and "a solver has a playable puzzle".
It is pure orchestration over two services already in this layer:

  * :class:`~puzzledesk.app.blocked.BlockedGenerateService` searches a legal layout
    and fills it above the quality bar (a complete search -- ``None`` is a UNSAT
    theorem, invariant "None is a proof", not a timeout);
  * :class:`~puzzledesk.app.cluing.ClueService` clues the filled grid through the
    :class:`~puzzledesk.app.clue.ClueProvider` port (the one soft, generative stage).

The service owns no I/O and no provider of its own -- it holds the two services and
threads a :class:`~puzzledesk.app.clue.ClueStyle` from its arguments. A ``None`` grid
propagates as a ``None`` puzzle, so the completeness epistemics survive the compose:
"no puzzle" here still means "no acceptable fill exists at this bar", never "gave up".
"""

from __future__ import annotations

from .blocked import BlockedGenerateService
from .clue import ClueStyle, Difficulty
from .cluing import CluedPuzzle, ClueService


class PuzzleService:
    """Generate a complete, clued puzzle: fill a blocked grid, then clue it."""

    def __init__(self, blocked: BlockedGenerateService, clue: ClueService) -> None:
        self._blocked = blocked
        self._clue = clue

    def generate(
        self,
        *,
        rows: int = 5,
        cols: int = 5,
        num_black: int = 4,
        min_score: float = 75.0,
        max_score: float | None = None,
        difficulty: Difficulty = Difficulty.WEDNESDAY,
        instructions: str = "",
        seed: int = 0,
        symmetric: bool = True,
        min_len: int = 3,
    ) -> CluedPuzzle | None:
        """Fill a ``rows``x``cols`` grid with ``num_black`` black cells drawing from the
        score band ``[min_score, max_score]``, then clue every entry at ``difficulty``.
        ``max_score`` (default None == a plain floor) turns the bar into an *obscurity
        band* -- a harder fill whose clues alone are insufficient, so the grid must carry
        the solve (D21/D26). ``None`` when no fill clears the band (complete search -- a
        genuine UNSAT, not a timeout)."""
        grid = self._blocked.fill_grid_once(
            rows,
            cols,
            num_black,
            min_score=min_score,
            max_score=max_score,
            seed=seed,
            symmetric=symmetric,
            min_len=min_len,
        )
        if grid is None:
            return None
        style = ClueStyle(difficulty=difficulty, instructions=instructions)
        return self._clue.clue(grid, style=style)
