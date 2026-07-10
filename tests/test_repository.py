"""InMemoryPuzzleRepository: the persistence port's first adapter (D34).

Drives the port with a real (fake-clued) CluedPuzzle, no files beyond the same
in-memory lexicon the PuzzleService tests use. Covers the save->get round-trip,
sequential ids, the total-port `None` for an unknown id, and that the in-memory
adapter structurally satisfies the runtime-checkable port.
"""

from __future__ import annotations

from fakes import FakeClueProvider, InMemoryLexiconSource, RecordingRngFactory

from puzzledesk.adapters.memory_repository import InMemoryPuzzleRepository
from puzzledesk.app.clue import ClueStyle
from puzzledesk.app.cluing import CluedPuzzle, ClueService
from puzzledesk.app.generate import GenerateService
from puzzledesk.app.puzzle_service import PuzzleService
from puzzledesk.app.repository import PuzzleRepository, StoredPuzzle
from puzzledesk.app.spec import CountLayout, GridSpec, PuzzleSpec
from puzzledesk.core.lexicon import Lexicon, MultiLexicon

# ab/cd across induce ac/bd down -- a genuinely distinct 2x2 fill (as in test_puzzle_service).
_FILLABLE = MultiLexicon({2: Lexicon(["ab", "cd", "ac", "bd"])})
_SPEC = PuzzleSpec(
    grid=GridSpec(rows=2, cols=2, min_score=0.0),
    layout=CountLayout(num_black=0, min_len=2),
    clue=ClueStyle(),
)


def _a_puzzle() -> CluedPuzzle:
    gen = GenerateService(InMemoryLexiconSource(multi=_FILLABLE), RecordingRngFactory())
    puzzle = PuzzleService(gen, ClueService(FakeClueProvider())).generate(_SPEC)
    assert puzzle is not None
    return puzzle


def test_save_then_get_round_trips() -> None:
    puzzle = _a_puzzle()
    repo = InMemoryPuzzleRepository()
    pid = repo.save(_SPEC, puzzle)
    stored = repo.get(pid)
    assert stored is not None
    assert isinstance(stored, StoredPuzzle)
    assert stored.id == pid
    assert stored.puzzle is puzzle
    assert stored.spec is _SPEC


def test_ids_are_sequential_and_distinct() -> None:
    puzzle = _a_puzzle()
    repo = InMemoryPuzzleRepository()
    first = repo.save(_SPEC, puzzle)
    second = repo.save(_SPEC, puzzle)
    assert (first, second) == ("1", "2")
    assert repo.get("1") is not None and repo.get("2") is not None


def test_unknown_id_is_none_not_a_raise() -> None:
    assert InMemoryPuzzleRepository().get("nope") is None


def test_adapter_satisfies_the_port() -> None:
    assert isinstance(InMemoryPuzzleRepository(), PuzzleRepository)
