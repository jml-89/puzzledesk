"""PuzzleService: the fill+clue composition, driven with injected fakes.

No model, no files, no global RNG -- an in-memory lexicon and the deterministic
``FakeClueProvider`` stand in. Covers the happy path (a filled grid comes back
clued), the completeness propagation (an unfillable list yields ``None`` -- a UNSAT
theorem survives the compose, it is not swallowed), and that the difficulty knob
threads through to the provider.
"""

from __future__ import annotations

from fakes import FakeClueProvider, InMemoryLexiconSource, RecordingRngFactory

from puzzledesk.app.blocked import BlockedGenerateService
from puzzledesk.app.clue import Difficulty
from puzzledesk.app.cluing import ClueService
from puzzledesk.app.puzzle_service import PuzzleService
from puzzledesk.core.lexicon import Lexicon, MultiLexicon

# ab/cd across induce ac/bd down: a genuinely distinct 2x2 fill exists.
_FILLABLE = MultiLexicon({2: Lexicon(["ab", "cd", "ac", "bd"])})
# one word can never fill four distinct slots -> the fill search returns None.
_UNFILLABLE = MultiLexicon({2: Lexicon(["ab"])})


def _service(multi: MultiLexicon) -> PuzzleService:
    blocked = BlockedGenerateService(InMemoryLexiconSource(multi=multi), RecordingRngFactory())
    return PuzzleService(blocked, ClueService(FakeClueProvider()))


def test_generate_returns_a_clued_puzzle_on_the_happy_path() -> None:
    puzzle = _service(_FILLABLE).generate(rows=2, cols=2, num_black=0, min_score=0.0, min_len=2)
    assert puzzle is not None
    # every derived entry got a clue, none left unclued
    assert set(puzzle.clues) == {t.id for t in puzzle.grid.runs()}
    assert puzzle.unclued == ()


def test_generate_propagates_none_when_nothing_fills() -> None:
    # legal layout exists, but the list admits no distinct fill -> None (a theorem,
    # not a timeout) must survive the compose rather than being swallowed.
    puzzle = _service(_UNFILLABLE).generate(rows=2, cols=2, num_black=0, min_score=0.0, min_len=2)
    assert puzzle is None


def test_generate_threads_difficulty_to_the_provider() -> None:
    # the FakeClueProvider stamps the difficulty name into each clue, so a Saturday
    # ask must surface as SATURDAY in the chosen clues.
    puzzle = _service(_FILLABLE).generate(
        rows=2, cols=2, num_black=0, min_score=0.0, min_len=2, difficulty=Difficulty.SATURDAY
    )
    assert puzzle is not None
    assert all("SATURDAY" in c.text for c in puzzle.clues.values())
