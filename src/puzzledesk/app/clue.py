"""The clue-generation port: turn a filled puzzle into clues, in a style.

Clue generation is the one *soft, generative* stage in a system that is otherwise
complete and deterministic (the solver's ``None`` is a UNSAT proof; nothing here
proves anything). So it is fenced behind a port and kept out of ``core`` entirely
-- the softness lives behind :class:`ClueProvider`, the app applies only
deterministic constraints on top. See docs/decisions.md D15.

Two axes (the reason this is a *strategy*):

  * **what** -- the data: a :class:`~puzzledesk.app.puzzle.FilledGrid` for context,
    and the :class:`~puzzledesk.app.puzzle.Target`\\ s to clue (the app decides
    *what* to clue -- usually ``grid.runs()``, optionally plus a meta target);
  * **how** -- the policy: a :class:`ClueStyle` (a sweepable difficulty knob plus
    free-form instructions carrying tone / theme / taboo words).

The provider generates; selection/ranking against hard constraints is the app's
job. Output is keyed by target identity (spatial), never by answer value.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol, runtime_checkable

from puzzledesk.app.puzzle import FilledGrid, Target, TargetId


class Difficulty(IntEnum):
    """The one *comparable* clue-difficulty knob -- ordered so it can be swept,
    like the acceptance-score bar. Named for the NYT week (Monday easiest)."""

    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6


@dataclass(frozen=True, slots=True)
class ClueStyle:
    """The *how* axis: policy for giving clues, independent of the words.
    ``difficulty`` is the sweepable knob; ``instructions`` is the free-form long
    tail (tone, spelling conventions, an imposed theme, taboo words)."""

    difficulty: Difficulty = Difficulty.WEDNESDAY
    instructions: str = ""


@dataclass(frozen=True, slots=True)
class Clue:
    """One clue. Identity (which target it clues) comes from the mapping key, so
    this stays minimal -- a metadata field (wordplay kind, self-rated difficulty)
    can be added later without touching the port."""

    text: str


@runtime_checkable
class ClueProvider(Protocol):
    """Clue ``targets`` in the context of ``grid``, in a ``style``.

    Returns up to ``n`` candidate clues per target, keyed by the target's spatial
    id. A target the provider cannot clue maps to an empty sequence -- never a
    raised error, so the port stays total. ``targets`` must be consistent with
    ``grid`` (their cells spell what the grid holds); ``grid.runs()`` guarantees
    this, and a meta target is built from the grid's own cells.
    """

    def clue(
        self,
        grid: FilledGrid,
        targets: Sequence[Target],
        *,
        style: ClueStyle,
        n: int = 1,
    ) -> Mapping[TargetId, Sequence[Clue]]: ...
