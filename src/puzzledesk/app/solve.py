"""The solve *session*: the deterministic environment a solver acts against.

This is the complete/deterministic half of the solving spike (D24), the mirror of
what ``app/cluing.py`` is to clue *generation*: a pure, testable state machine with
no model and no network. A soft, generative *solver* (the LLM agent) lives behind
the :class:`~puzzledesk.app.solver.SolverAgent` port and drives this session through
the :class:`~puzzledesk.app.solve_service.SolveService` harness; here there is only
bookkeeping and a checker.

The object model, smallest-thing-that-works:

  * :class:`Board` -- the static truth: geometry, clues, and the **answer key**.
    Built once from a :class:`~puzzledesk.app.cluing.CluedPuzzle`. The answer key
    lives *here* and nowhere the agent can see it.
  * :class:`SolveState` -- ``Board`` + the solver's per-*entry* guesses. A cell's
    letter is *derived* from the entries that pass through it (D15's "derive views"
    rule again), which is what makes a **crossing conflict** -- two crossing guesses
    disagreeing on a shared cell -- a signal the solver can see with *no* answer key.
  * :class:`SolveView` -- the answer-free projection handed to the agent: the grid
    geometry, the clues, the solver's own current letters, and the feedback the
    policy revealed. It carries no unguessed answer, ever -- the integrity invariant
    of the whole experiment (a solver that can read the key measures nothing).

Feedback is a **policy knob**, and that knob *is* a solver-skill dial -- the same
role ``gimme`` plays in the analytical ``difficulty.solve_order`` model (D22):

  * ``CELL``   -- per-cell right/wrong for the solver's own filled cells (the NYT
    "check" button). The default: generous, a clear loop. Note it is autocheck-on,
    so it compresses the difficulty signal -- the stricter policies below are the
    sharper probes.
  * ``WORD``   -- whole-entry right/wrong for fully-filled entries.
  * ``CROSSING`` -- only the cells where two crossing guesses disagree. Uses **no**
    answer key at all -- pure internal consistency, the most authentic no-cheating
    crossword signal.
  * ``NONE``   -- nothing but the terminal "solved" bit. The purest probe, the
    weakest loop.

None of this proves anything (unlike the fill engines' ``None``): a solver that runs
out of turns has *not* shown the puzzle unsolvable, only that it did not get there in
the budget. That honesty is enforced in the harness, not here (see D23's parallel).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

from .cluing import CluedPuzzle
from .puzzle import Cell

EntryRef = tuple[int, str]
"""The solver-facing identity of an entry: ``(clue number, "A"|"D")`` -- friendlier
than the spatial ``TargetId`` (start cell + kind) the cluing side keys on."""


class FeedbackPolicy(Enum):
    """What the session reveals after a move -- the solver-skill knob (see module doc)."""

    CELL = "cell"
    WORD = "word"
    CROSSING = "crossing"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class _Entry:
    """One entry's static facts, including its answer (oracle -- never leaves ``Board``)."""

    ref: EntryRef
    cells: tuple[Cell, ...]
    answer: str
    clue: str  # "" when the provider could not clue it (honest, not hidden)

    @property
    def number(self) -> int:
        return self.ref[0]

    @property
    def direction(self) -> str:
        return self.ref[1]


@dataclass(frozen=True, slots=True)
class Board:
    """The static solve board: geometry + clues + the answer key. Built once from a
    clued puzzle; the answer key is quarantined here and projected *out* of every
    :class:`SolveView`."""

    rows: int
    cols: int
    black: tuple[Cell, ...]
    entries: tuple[_Entry, ...]

    @classmethod
    def of(cls, puzzle: CluedPuzzle) -> Board:
        grid = puzzle.grid
        numbering = grid.numbering()
        black = tuple(
            (r, c) for r in range(grid.rows) for c in range(grid.cols) if grid.cells[r][c] is None
        )
        entries = tuple(
            _Entry(
                ref=(numbering[t.cells[0]], t.kind),
                cells=t.cells,
                answer=t.answer,
                clue=(clue.text if (clue := puzzle.clues.get(t.id)) is not None else ""),
            )
            for t in grid.runs()
        )
        return cls(rows=grid.rows, cols=grid.cols, black=black, entries=entries)

    def entry(self, ref: EntryRef) -> _Entry | None:
        return next((e for e in self.entries if e.ref == ref), None)

    def length_of(self, ref: EntryRef) -> int | None:
        e = self.entry(ref)
        return len(e.cells) if e is not None else None


@dataclass(frozen=True, slots=True)
class Feedback:
    """What a :class:`FeedbackPolicy` revealed about the current state. Only the fields
    the policy populates are non-empty; the rest stay ``()``. ``solved`` is revealed
    under *every* policy (it is the win condition, not a leak)."""

    policy: FeedbackPolicy
    solved: bool
    correct_cells: tuple[Cell, ...] = ()
    wrong_cells: tuple[Cell, ...] = ()
    correct_entries: tuple[EntryRef, ...] = ()
    wrong_entries: tuple[EntryRef, ...] = ()
    conflicts: tuple[Cell, ...] = ()


@dataclass(frozen=True, slots=True)
class EntryView:
    """One entry as the solver sees it: its cells (geometry is public), its clue, and
    the letters *it has filled so far* (``None`` per blank cell). Never its answer."""

    number: int
    direction: str
    clue: str
    cells: tuple[Cell, ...]
    letters: tuple[str | None, ...]

    @property
    def length(self) -> int:
        return len(self.letters)

    @property
    def pattern(self) -> str:
        """The fill as a readable pattern, blanks as ``_`` (e.g. ``S_B_``)."""
        return "".join((ch.upper() if ch is not None else "_") for ch in self.letters)


@dataclass(frozen=True, slots=True)
class SolveView:
    """The answer-free snapshot handed to a :class:`~puzzledesk.app.solver.SolverAgent`.

    Everything the agent is *allowed* to know: the grid shape, the black cells, the
    Across/Down entries with their clues and current letters, and the feedback the
    policy last revealed. It is a pure function of the state -- so the agent stays a
    function of observable state, and re-deriving it every turn needs no hidden log.
    """

    rows: int
    cols: int
    black: tuple[Cell, ...]
    across: tuple[EntryView, ...]
    down: tuple[EntryView, ...]
    feedback: Feedback

    def letter_grid(self) -> tuple[tuple[str | None, ...], ...]:
        """The display grid: ``None`` per black square, ``""`` per blank white cell,
        else the solver's current letter. Pure geometry + the solver's own fill -- no
        answer key."""
        black = set(self.black)
        letters: dict[Cell, str] = {}
        for e in (*self.across, *self.down):
            for cell, ch in zip(e.cells, e.letters, strict=True):
                if ch is not None:
                    letters[cell] = ch
        return tuple(
            tuple(None if (r, c) in black else letters.get((r, c), "") for c in range(self.cols))
            for r in range(self.rows)
        )


@dataclass(frozen=True, slots=True)
class SolveState:
    """A ``Board`` plus the solver's per-entry guesses. Immutable: every transition
    returns a fresh state, so the harness keeps an honest history for free."""

    board: Board
    guesses: tuple[tuple[EntryRef, str], ...] = ()

    @classmethod
    def initial(cls, board: Board) -> SolveState:
        return cls(board=board, guesses=())

    def _guess_map(self) -> dict[EntryRef, str]:
        return dict(self.guesses)

    def with_guess(self, ref: EntryRef, word: str) -> SolveState:
        """Set (or, with ``word=""``, clear) the guess for ``ref``. Assumes ``ref`` is a
        real entry and ``word`` fits its length -- the harness validates before calling,
        so a bad move is rejected there, not stored here."""
        g = self._guess_map()
        if word:
            g[ref] = word.lower()
        else:
            g.pop(ref, None)
        return SolveState(board=self.board, guesses=tuple(sorted(g.items())))

    # --- derivations -------------------------------------------------------------

    def cell_letters(self) -> tuple[dict[Cell, str], set[Cell]]:
        """Resolve each white cell's letter from the entries through it, and flag the
        **conflict** cells where a crossing across/down guess disagree. The interlock
        is derived, never stored -- and the conflict set needs no answer key."""
        contrib: dict[Cell, set[str]] = defaultdict(set)
        for ref, word in self.guesses:
            e = self.board.entry(ref)
            if e is None or len(word) != len(e.cells):
                continue
            for cell, ch in zip(e.cells, word, strict=True):
                contrib[cell].add(ch)
        letters: dict[Cell, str] = {}
        conflicts: set[Cell] = set()
        for cell, chs in contrib.items():
            letters[cell] = sorted(chs)[0]
            if len(chs) > 1:
                conflicts.add(cell)
        return letters, conflicts

    def is_solved(self) -> bool:
        """Every white cell filled, no crossing conflict, and every letter matches the
        answer key. Cell-based, not per-entry: a crossword is solved when the *grid* is
        right -- filling the acrosses correctly already fills their crossing downs, which
        is exactly the interlock, so there is nothing extra to 'submit'."""
        letters, conflicts = self.cell_letters()
        if conflicts:
            return False
        return all(letters.get(cell) == ch for cell, ch in self._oracle_cells().items())

    def feedback(self, policy: FeedbackPolicy) -> Feedback:
        """Check the current state under ``policy``. Only reveals the solver's *own*
        filled cells/entries -- never an unguessed answer (see the integrity invariant)."""
        letters, conflicts = self.cell_letters()
        oracle = self._oracle_cells()
        solved = self.is_solved()
        if policy is FeedbackPolicy.CROSSING:
            return Feedback(policy, solved, conflicts=tuple(sorted(conflicts)))
        if policy is FeedbackPolicy.CELL:
            correct = tuple(
                sorted(c for c, ch in letters.items() if c not in conflicts and ch == oracle[c])
            )
            wrong = tuple(
                sorted(c for c, ch in letters.items() if c not in conflicts and ch != oracle[c])
            )
            return Feedback(policy, solved, correct_cells=correct, wrong_cells=wrong)
        if policy is FeedbackPolicy.WORD:
            g = self._guess_map()
            done = [e for e in self.board.entries if len(g.get(e.ref, "")) == len(e.cells)]
            correct_e = tuple(e.ref for e in done if g[e.ref] == e.answer)
            wrong_e = tuple(e.ref for e in done if g[e.ref] != e.answer)
            return Feedback(policy, solved, correct_entries=correct_e, wrong_entries=wrong_e)
        return Feedback(policy, solved)  # NONE

    def _oracle_cells(self) -> dict[Cell, str]:
        out: dict[Cell, str] = {}
        for e in self.board.entries:
            for cell, ch in zip(e.cells, e.answer, strict=True):
                out[cell] = ch
        return out

    def view(self, policy: FeedbackPolicy) -> SolveView:
        """Project the answer-free :class:`SolveView` the agent acts on."""
        letters, _ = self.cell_letters()

        def entry_view(e: _Entry) -> EntryView:
            return EntryView(
                number=e.number,
                direction=e.direction,
                clue=e.clue,
                cells=e.cells,
                letters=tuple(letters.get(cell) for cell in e.cells),
            )

        across = tuple(entry_view(e) for e in self.board.entries if e.direction == "A")
        down = tuple(entry_view(e) for e in self.board.entries if e.direction == "D")
        return SolveView(
            rows=self.board.rows,
            cols=self.board.cols,
            black=self.board.black,
            across=_ordered(across),
            down=_ordered(down),
            feedback=self.feedback(policy),
        )


def _ordered(entries: tuple[EntryView, ...]) -> tuple[EntryView, ...]:
    return tuple(sorted(entries, key=lambda e: e.number))
