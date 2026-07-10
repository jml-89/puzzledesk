"""In-memory ``PuzzleRepository`` -- a dict plus a counter.

The first implementation of the persistence port (D34, roadmap Phase 1). A database
adapter is a drop-in *second* implementation of the very same port -- and that the
swap is drop-in, with no change above this layer, is exactly what the port buys.

State lives only in the process, so it is lost on restart: right for the loop's
first slice (develop the API, prove the round-trip) and for tests, not for
production, where the DB adapter takes over.
"""

from __future__ import annotations

from itertools import count

from puzzledesk.app.cluing import CluedPuzzle
from puzzledesk.app.repository import PuzzleId, StoredPuzzle
from puzzledesk.app.spec import PuzzleSpec


class InMemoryPuzzleRepository:
    """A :class:`~puzzledesk.app.repository.PuzzleRepository` backed by a dict.

    Ids are sequential decimal strings (``"1"``, ``"2"``, ...) from a monotonic
    counter -- opaque to callers, predictable for tests. Not thread-safe; the
    single-process dev server never contends, and the DB adapter owns concurrency.
    """

    def __init__(self) -> None:
        self._store: dict[PuzzleId, StoredPuzzle] = {}
        self._ids = count(1)

    def save(self, spec: PuzzleSpec, puzzle: CluedPuzzle) -> PuzzleId:
        pid: PuzzleId = str(next(self._ids))
        self._store[pid] = StoredPuzzle(id=pid, spec=spec, puzzle=puzzle)
        return pid

    def get(self, puzzle_id: PuzzleId) -> StoredPuzzle | None:
        return self._store.get(puzzle_id)
