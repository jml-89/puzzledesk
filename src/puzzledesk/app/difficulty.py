"""Structural difficulty: which crossings a solver cannot get from the grid alone.

``validate`` (core) scores a grid's *quality* -- per-word crowd score plus
distinctness. Difficulty is a separate, layered thing (docs/decisions.md D21); this
module is its one *complete, deterministic* structural slice.

The idea: a dense mini solves as a percolation cascade -- get the gettable entries,
they donate letters to their crossings, neighbours' effective difficulty collapses,
the grid unzips. The cascade stalls at a **Natick**: a cell where two entries cross
and *neither word pins the shared letter*, so the only way to get it is to already
know one of the two entries. That stall is computable with no solve data: for each
crossing cell, free that cell in the across word and count the distinct letters the
rest of the across word still admits, likewise for the down word. If either count is
1, the letter is **forced** (that direction determines it); otherwise the crossing is
**open** -- the difficulty a grid of merely-obscure words can still hide, and the
easy-crossings a grid of rare words can still unzip through.

Two modelling choices live at the *call site*, not here (D21):

  * **Full vocabulary.** ``options`` is wired against the solver's whole lexicon (the
    unfiltered list), not the generation-filtered one -- a solver knows every word.
  * **Maximal support.** The rest of each word is assumed known, so an open crossing
    is *unavoidably* hard regardless of solve order. A conservative signal, not a
    solve-trajectory simulation (that is a deferred spike; see open-questions).

``analyze`` imports nothing from ``core``: it takes an ``options(answer, pos)``
callable, so it is representation-agnostic (square or blocked both project into
:class:`~puzzledesk.app.puzzle.FilledGrid`, invariant 0) and trivially fakeable.
``scripts/difficulty.py`` wires it to ``Lexicon.n_letters_at`` and adds the per-word
obscurity read (openness x low score = the unfair Natick).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from puzzledesk.app.puzzle import Cell, FilledGrid, TargetId

Options = Callable[[str, int], int]
"""``options(answer, pos)`` -> how many distinct letters the lexicon admits at ``pos``
if that cell of ``answer`` were blanked and the rest held fixed. ``1`` == the word
alone forces the letter there. Wired to ``Lexicon.n_letters_at`` in production."""


@dataclass(frozen=True, slots=True)
class CrossingOpenness:
    """One crossing cell and how pinned its shared letter is.

    ``across_options``/``down_options`` are the distinct letters each word alone admits
    at this cell (from :data:`Options`). The letter is **forced** iff one of them is 1;
    otherwise the crossing is **open** and the solver needs outside knowledge to get it.
    """

    cell: Cell
    across: TargetId
    down: TargetId
    across_options: int
    down_options: int

    @property
    def ambiguity(self) -> int:
        """The min of the two option counts: 1 == some direction pins the letter,
        higher == both directions leave it open (harder). 0 only if a word is absent
        from the analysis lexicon (a degenerate case, surfaced not hidden)."""
        return min(self.across_options, self.down_options)

    @property
    def forced(self) -> bool:
        """True iff one of the two words alone determines the shared letter."""
        return self.across_options == 1 or self.down_options == 1

    @property
    def is_open(self) -> bool:
        """True iff neither word pins the letter -- a Natick risk."""
        return not self.forced


@dataclass(frozen=True, slots=True)
class StructuralDifficulty:
    """The per-crossing openness of a whole grid, and the aggregates worth reporting."""

    crossings: tuple[CrossingOpenness, ...]

    @property
    def open_crossings(self) -> tuple[CrossingOpenness, ...]:
        """The crossings no single word pins -- the structural difficulty hotspots."""
        return tuple(c for c in self.crossings if c.is_open)

    @property
    def max_ambiguity(self) -> int:
        """The worst crossing's ambiguity (0 for a grid with no crossings)."""
        return max((c.ambiguity for c in self.crossings), default=0)

    @property
    def hardest(self) -> CrossingOpenness | None:
        """The most ambiguous crossing (the likeliest Natick), or None if no crossings."""
        return max(self.crossings, key=lambda c: c.ambiguity, default=None)


def analyze(grid: FilledGrid, options: Options) -> StructuralDifficulty:
    """Report the structural openness of every crossing in ``grid``.

    Deterministic and complete over the crossings; ``options`` supplies the per-word
    letter counts (see :data:`Options` and this module's docstring for the two
    modelling choices its wiring encodes).
    """
    out: list[CrossingOpenness] = []
    for x in grid.crossings():
        a_pos = x.a.cells.index(x.cell)
        d_pos = x.b.cells.index(x.cell)
        out.append(
            CrossingOpenness(
                cell=x.cell,
                across=x.a.id,
                down=x.b.id,
                across_options=options(x.a.answer, a_pos),
                down_options=options(x.b.answer, d_pos),
            )
        )
    return StructuralDifficulty(tuple(out))


# --- Solve order: the dynamic reading (D22) --------------------------------------
#
# ``analyze`` is a *snapshot* at maximal support. A human does not solve at maximal
# support -- they uncover entries easiest-first, and each entry they get donates its
# letters to the crossing entries, so support *arrives over time* (a percolation
# cascade). ``solve_order`` replays the *known* fill in that human order and measures
# where the order forces a hard get. It is not a solver (we have a complete one); it
# is a difficulty *model* over an already-solved grid, so it never backtracks.
#
# The step kinds encode the three ways a human gets an entry:
#   * ``forced`` -- only one word fits its current pattern; free, pure logic, no clue.
#   * ``gimme``  -- common enough (score >= ``gimme``) to just know from the clue.
#   * ``hard``   -- neither: the solver is stuck and must work an obscure, still-open
#                   entry from its clue, disambiguating among ``candidates`` fits.
#
# The payoff over ``analyze``: an obscure word whose crossings *force* it by the time
# the solver reaches it is not a Natick -- ``analyze`` (maximal support) cannot tell
# that from a genuinely open one, but the cascade can. ``gimme`` is the soft
# clue-gettability knob (D21 layer B), still uncalibrated -- so it is an input, and
# the model brackets a real solver rather than claiming to be one.

Candidates = Callable[[str, frozenset[int]], int]
"""``candidates(answer, known)`` -> how many words fit ``answer``'s pattern when the
positions in ``known`` are pinned to its letters and the rest are blank. ``1`` == the
entry is forced by its crossings so far. Wired to ``Lexicon.matching`` in production."""


@dataclass(frozen=True, slots=True)
class Step:
    """One entry solved, in human order: why it was gettable and how hard."""

    order: int
    target: TargetId
    answer: str
    kind: str  # "forced" | "gimme" | "hard"
    candidates: int  # words fitting its pattern at the moment it was solved
    score: float


@dataclass(frozen=True, slots=True)
class Trajectory:
    """The full easiest-first solve of one grid: the effort curve and its bottleneck."""

    steps: tuple[Step, ...]

    def of_kind(self, kind: str) -> tuple[Step, ...]:
        return tuple(s for s in self.steps if s.kind == kind)

    @property
    def hard_gets(self) -> tuple[Step, ...]:
        """The steps where the solver stalled -- obscure *and* still under-supported."""
        return self.of_kind("hard")

    @property
    def bottleneck(self) -> Step | None:
        """The hardest hard-get (most fits to disambiguate, ties to the more obscure),
        or None if the grid solved with no stall. This is what makes it a Saturday."""
        hard = self.hard_gets
        return max(hard, key=lambda s: (s.candidates, -s.score)) if hard else None


def solve_order(
    grid: FilledGrid, candidates: Candidates, score: Callable[[str], float], *, gimme: float
) -> Trajectory:
    """Replay ``grid``'s fill easiest-first and record the effort at each step.

    Each iteration solves one entry: a forced one if any (a unique fit), else the most
    common still-unsolved gimme (score >= ``gimme``), else -- stuck -- the least-bad
    hard get (highest score, fewest fits). Solving an entry reveals its cells, which
    can force or ease its crossings next iteration (the cascade). Deterministic:
    ``grid.runs()`` order breaks every tie.
    """
    entries = grid.runs()
    # A cell is "known" once any entry through it is solved; since crossing entries
    # share that cell, revealing a solved entry's cells propagates to its crossings.
    known: set[Cell] = set()
    solved: set[TargetId] = set()
    steps: list[Step] = []
    while len(solved) < len(entries):
        pending = [t for t in entries if t.id not in solved]
        fits = {
            t.id: candidates(t.answer, frozenset(i for i, c in enumerate(t.cells) if c in known))
            for t in pending
        }
        forced = [t for t in pending if fits[t.id] == 1]
        if forced:
            pick, kind = forced[0], "forced"
        else:
            gimmes = [t for t in pending if score(t.answer) >= gimme]
            if gimmes:
                pick, kind = max(gimmes, key=lambda t: score(t.answer)), "gimme"
            else:
                # Stuck: attack the most-supported entry (fewest fits), ties to the
                # one you are likelier to know (higher score). So support -- not raw
                # obscurity -- drives the cascade; only the ice-breaking first get is
                # truly cold.
                pick = max(pending, key=lambda t: (-fits[t.id], score(t.answer)))
                kind = "hard"
        steps.append(
            Step(len(steps), pick.id, pick.answer, kind, fits[pick.id], score(pick.answer))
        )
        solved.add(pick.id)
        known.update(pick.cells)
    return Trajectory(tuple(steps))
