"""Difficulty contracts (D20): the score band and structural checkability.

Both slices are *complete and deterministic*, so they get tests (not benchmarks):
the band filter keeps exactly the in-range words, and ``analyze`` flags a crossing as
*open* iff neither crossing word alone pins the shared letter -- the Natick signal.
"""

from __future__ import annotations

from fakes import InMemoryLexiconSource, RecordingRngFactory

from puzzledesk.app.difficulty import analyze
from puzzledesk.app.mini import MiniService
from puzzledesk.app.puzzle import FilledGrid
from puzzledesk.core.lexicon import Lexicon

# --- A. word prior: the two-sided score band -------------------------------------


def test_filtered_band_keeps_only_in_range_words() -> None:
    lex = Lexicon(["aa", "bb", "cc", "dd"], [10.0, 40.0, 70.0, 100.0])
    floor = lex.filtered(40.0)  # one-sided: >= 40
    assert set(floor.words) == {"bb", "cc", "dd"}
    band = lex.filtered(40.0, 70.0)  # two-sided: [40, 70]
    assert set(band.words) == {"bb", "cc"}


# ab/cd across induce ac/bd down (as in test_services); scores put all four in a band.
_SCORED = Lexicon(["ab", "cd", "ac", "bd"], [60.0, 65.0, 70.0, 75.0])


def _service(lex: Lexicon) -> MiniService:
    return MiniService(InMemoryLexiconSource(single={2: lex}), RecordingRngFactory())


def test_service_threads_the_band() -> None:
    batch = _service(_SCORED).generate(2, min_score=60.0, max_score=80.0, count=1)
    assert batch.max_score == 80.0
    assert batch.eligible == 4  # all four words fall in [60, 80]
    assert batch.results  # so a distinct square exists
    r = batch.results[0]
    assert all(60.0 <= w.score <= 80.0 for w in r.across + r.down)


def test_band_upper_bound_can_starve_the_grid() -> None:
    # Raising the floor past ab(60)/cd(65) leaves only ac/bd -- no square is possible.
    batch = _service(_SCORED).generate(2, min_score=66.0, max_score=80.0, count=1)
    assert batch.eligible == 2
    assert not batch.results  # honest UNSAT, not an error


# --- A'. structural checkability: n_letters_at + analyze --------------------------


def test_n_letters_at_forced_vs_open() -> None:
    lex = Lexicon(["cat", "cot", "cut", "car"])
    # middle of "cat": c_t admits a/o/u -> three letters, the word does not pin it.
    assert lex.n_letters_at("cat", 1) == 3
    # middle of "car": c_r admits only 'a' -> forced by the word alone.
    assert lex.n_letters_at("car", 1) == 1
    # first of "cat": _at admits only 'c'.
    assert lex.n_letters_at("cat", 0) == 1


def test_analyze_flags_the_open_crossing() -> None:
    # A fake options oracle: exactly cell (0,0) is left open (2 letters each way);
    # every other crossing has a direction that pins it (1).
    opts = {
        ("ab", 0): 3,
        ("ab", 1): 1,
        ("cd", 0): 1,
        ("cd", 1): 1,
        ("ac", 0): 2,
        ("ac", 1): 1,
        ("bd", 0): 1,
        ("bd", 1): 1,
    }
    grid = FilledGrid((("a", "b"), ("c", "d")))
    diff = analyze(grid, lambda w, p: opts[(w, p)])

    assert len(diff.crossings) == 4  # a fully-checked 2x2 has four crossings
    assert len(diff.open_crossings) == 1
    only = diff.open_crossings[0]
    assert only.cell == (0, 0)
    assert only.is_open and not only.forced
    assert only.ambiguity == 2
    assert diff.max_ambiguity == 2
    assert diff.hardest is only
    # a forced crossing reports forced/not-open
    c11 = next(c for c in diff.crossings if c.cell == (1, 1))
    assert c11.forced and not c11.is_open


def test_analyze_wired_to_a_real_lexicon() -> None:
    # "?b" -> {ab, cb} and "?c" -> {ac, bc}, so the shared 'a' at (0,0) is unpinned
    # from both directions: a genuine open crossing computed via n_letters_at.
    lex = Lexicon(["ab", "cd", "ac", "bd", "cb", "bc"])
    grid = FilledGrid((("a", "b"), ("c", "d")))
    diff = analyze(grid, lambda w, p: lex.n_letters_at(w, p))

    c00 = next(c for c in diff.crossings if c.cell == (0, 0))
    assert c00.across_options == 2  # ab / cb
    assert c00.down_options == 2  # ac / bc
    assert c00.is_open
    assert diff.hardest is not None and diff.hardest.cell == (0, 0)
