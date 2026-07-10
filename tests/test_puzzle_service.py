"""PuzzleService: the fill+clue composition, driven with injected fakes.

No model, no files, no global RNG -- an in-memory lexicon and the deterministic
``FakeClueProvider`` stand in. Covers the happy path (a filled grid comes back
clued), the completeness propagation (an unfillable list yields ``None`` -- a UNSAT
theorem survives the compose, it is not swallowed), and that the difficulty knob
threads through to the provider.
"""

from __future__ import annotations

from fakes import FakeClueProvider, InMemoryLexiconSource, RecordingRngFactory

from puzzledesk.app.clue import ClueStyle, Difficulty
from puzzledesk.app.cluing import ClueService
from puzzledesk.app.generate import GenerateService
from puzzledesk.app.puzzle_service import PuzzleService
from puzzledesk.app.spec import CountLayout, GridSpec, PuzzleSpec
from puzzledesk.core.lexicon import Lexicon, MultiLexicon

# ab/cd across induce ac/bd down: a genuinely distinct 2x2 fill exists.
_FILLABLE = MultiLexicon({2: Lexicon(["ab", "cd", "ac", "bd"])})
# one word can never fill four distinct slots -> the fill search returns None.
_UNFILLABLE = MultiLexicon({2: Lexicon(["ab"])})


def _service(multi: MultiLexicon) -> PuzzleService:
    generator = GenerateService(InMemoryLexiconSource(multi=multi), RecordingRngFactory())
    return PuzzleService(generator, ClueService(FakeClueProvider()))


def _spec(
    *, max_score: float | None = None, difficulty: Difficulty = Difficulty.WEDNESDAY
) -> PuzzleSpec:
    # A fully-checked 2x2 is a 0-black count layout with min_len 2 (the curated data has
    # no 2-letter entries, but the in-memory fakes do).
    return PuzzleSpec(
        grid=GridSpec(rows=2, cols=2, min_score=0.0, max_score=max_score),
        layout=CountLayout(num_black=0, min_len=2),
        clue=ClueStyle(difficulty=difficulty),
    )


def test_generate_returns_a_clued_puzzle_on_the_happy_path() -> None:
    puzzle = _service(_FILLABLE).generate(_spec())
    assert puzzle is not None
    # every derived entry got a clue, none left unclued
    assert set(puzzle.clues) == {t.id for t in puzzle.grid.runs()}
    assert puzzle.unclued == ()


def test_generate_propagates_none_when_nothing_fills() -> None:
    # legal layout exists, but the list admits no distinct fill -> None (a theorem,
    # not a timeout) must survive the compose rather than being swallowed.
    puzzle = _service(_UNFILLABLE).generate(_spec())
    assert puzzle is None


def test_generate_accepts_a_score_band() -> None:
    # the obscurity band [min, max] threads through generate -> fill_grid -> _count
    # without disturbing the happy path (D26).
    puzzle = _service(_FILLABLE).generate(_spec(max_score=100.0))
    assert puzzle is not None


def test_generate_threads_difficulty_to_the_provider() -> None:
    # the FakeClueProvider stamps the difficulty name into each clue, so a Saturday
    # ask must surface as SATURDAY in the chosen clues.
    puzzle = _service(_FILLABLE).generate(_spec(difficulty=Difficulty.SATURDAY))
    assert puzzle is not None
    assert all("SATURDAY" in c.text for c in puzzle.clues.values())
