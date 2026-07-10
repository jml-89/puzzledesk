"""Persistence port: store a generated puzzle, read it back by id.

The "get a previously created puzzle" seam the roadmap names (Phase 1, D34). A
*port* declared in ``app`` -- the application states the capability it needs; the
infrastructure (``adapters``) implements it. This is the "Second adapters" seam
``open-questions.md`` reserved, finally exercised: an in-memory implementation now,
a database one later, both behind this one interface.

The determinism nuance D34 flagged is why we store *data*, not a spec to re-run:
the *fill* is reproducible from ``(lists, spec, seed)`` (the complete engines are
deterministic), but the *clues* are **soft** (an LLM), so regenerating from the
spec would not reproduce the same puzzle. We therefore keep the whole
:class:`~puzzledesk.app.cluing.CluedPuzzle`, alongside the
:class:`~puzzledesk.app.spec.PuzzleSpec` that requested it (provenance -- *what was
asked for*), under an id the repository assigns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from puzzledesk.app.cluing import CluedPuzzle
from puzzledesk.app.spec import PuzzleSpec

#: An opaque handle to a stored puzzle. The scheme is the adapter's business (a
#: counter in memory, a row id / uuid in a database); callers treat it as opaque.
PuzzleId = str


@dataclass(frozen=True, slots=True)
class StoredPuzzle:
    """A persisted puzzle: the clued aggregate, plus the spec that requested it
    (provenance), under the id the repository assigned."""

    id: PuzzleId
    spec: PuzzleSpec
    puzzle: CluedPuzzle


@runtime_checkable
class PuzzleRepository(Protocol):
    """Save a clued puzzle (returning its assigned id) and fetch one by id.

    ``get`` returns ``None`` for an unknown id -- a **total** port, never a raise,
    so a caller words "no such puzzle" itself (the CLI/API decides the 404), the
    same shape as :class:`~puzzledesk.app.clue.ClueProvider` returning empties
    rather than raising.
    """

    def save(self, spec: PuzzleSpec, puzzle: CluedPuzzle) -> PuzzleId:
        """Persist ``puzzle`` (with its originating ``spec``); return its new id."""
        ...

    def get(self, puzzle_id: PuzzleId) -> StoredPuzzle | None:
        """The stored puzzle for ``puzzle_id``, or ``None`` if there is none."""
        ...
