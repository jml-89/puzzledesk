"""The clue-generation use-case: grid in, clued puzzle out.

Pure orchestration over the :class:`~puzzledesk.app.clue.ClueProvider` port -- the
deterministic half of the soft/generative split (D15). The *provider* generates
candidates (behind the port, where the softness lives); this service applies only
**hard, deterministic** constraints and a deterministic selection policy, so it is
fully testable with an in-memory fake and no model.

The hard constraint set is deliberately minimal and universal: a clue must be
non-empty and must not contain its own answer (the one rule every crossword obeys).
Softer rules -- no cross-answer leak, no duplicated clue form, difficulty
calibration -- are judgment calls that belong to the provider or a future
``ClueRanker``, not here. Selection is "first surviving candidate" (providers order
best-first); a target whose every candidate is rejected is reported ``unclued``
rather than silently given a bad clue.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .clue import Clue, ClueProvider, ClueStyle
from .puzzle import FilledGrid, Target, TargetId


@dataclass(frozen=True, slots=True)
class CluedPuzzle:
    """A filled grid with a chosen clue per target, plus the targets no acceptable
    clue could be found for (honest about what the provider could not clue)."""

    grid: FilledGrid
    clues: Mapping[TargetId, Clue]
    unclued: tuple[TargetId, ...]


class ClueService:
    """Clue a filled grid: ask the provider for candidates per target, keep the
    first that clears the hard constraints, and report the rest as unclued."""

    def __init__(self, provider: ClueProvider, *, candidates: int = 3) -> None:
        self._provider = provider
        self._candidates = candidates

    def clue(
        self,
        grid: FilledGrid,
        *,
        style: ClueStyle,
        targets: Sequence[Target] | None = None,
    ) -> CluedPuzzle:
        """Clue ``targets`` (default: every entry, ``grid.runs()``; pass extra
        targets to clue a meta) in ``style``."""
        ts = tuple(targets) if targets is not None else grid.runs()
        candidates = self._provider.clue(grid, ts, style=style, n=self._candidates)

        chosen: dict[TargetId, Clue] = {}
        unclued: list[TargetId] = []
        for t in ts:
            pick = _first_acceptable(candidates.get(t.id, ()), t.answer)
            if pick is None:
                unclued.append(t.id)
            else:
                chosen[t.id] = pick
        return CluedPuzzle(grid=grid, clues=chosen, unclued=tuple(unclued))


def _first_acceptable(candidates: Sequence[Clue], answer: str) -> Clue | None:
    """The first candidate clearing the hard constraints: non-empty, and not
    containing its own answer (case-insensitive substring). Providers order
    best-first, so first-acceptable is the selection policy."""
    lowered = answer.lower()
    for c in candidates:
        text = c.text.strip()
        if text and lowered not in text.lower():
            return c
    return None
