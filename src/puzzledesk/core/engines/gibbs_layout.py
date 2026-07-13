"""Gibbs/energy layout sampler -- the black-cell field, sampled not searched (D27).

Everywhere else the system *searches*: fill (fill.py) and the layout generators
(patterns.py) are complete backtracking, because word fill is a hard-bar CSP where
completeness wins (D7) and a ``None`` is a UNSAT *theorem*. The black-cell **layout**
is the opposite regime, and docs/open-questions.md ("Layout generation is a soft,
local field") argued it for a while before anyone built it:

  * it is a **translation-invariant grid** with **local run-length legality** and a
    **soft, statistical objective** -- density, spread, no 2x2 black blocks;
  * every density knob D25 reached for (a white bias, a black-fraction target, an
    anti-cluster penalty) is a *local kernel applied uniformly across the grid* -- the
    tell that the object is a **field with local factors** (an Ising/Potts energy
    model), not something to hand-tune inside a systematic search;
  * it *stiffens near a critical density* -- the D25 runaway backtracking as
    ``max_black`` approached the feasibility minimum is textbook SAT/UNSAT
    phase-transition hardness, exactly where a complete solver chokes and a sampler is
    at home.

So this is the **"big-and-soft" regime D19 reserved** for the sampler's return -- a
*fresh spike with a new hypothesis* (the layout, not the fill), not a resurrection of
the retired fill sampler. The energy is a sum of local factors; we draw from
``exp(-E/T)`` by annealed Gibbs over the binary field.

The honest boundary the docs flagged holds here:

  * **symmetry is global but free** -- we sample only the 180°-rotation orbit
    representatives and colour the whole orbit at once, so every sample is symmetric by
    construction (no factor, no penalty);
  * **connectivity is global and topological** -- a local factor genuinely cannot
    express "all white cells form one region", so it is *not* in the energy. It is a
    global **reject** at the end (BFS via ``patterns._connected``): a sample that comes
    out disconnected is discarded, and the caller draws another.

Because it is a sampler, its epistemics are the mirror of the searchers': a sample is
a *legal layout when one is returned*, but "no sample after N attempts" is **budget
exhaustion, never a proof** (that is what ``patterns.capped_layout_exists`` is for).
The final legality gate (:func:`_finalize`) reuses ``patterns``' own predicates, so a
yielded grid is legal by exactly the definition ``gen_capped`` guarantees.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass

from puzzledesk.core.blocked import BlockedGrid
from puzzledesk.core.engines import fill
from puzzledesk.core.engines.patterns import _connected, _fully_checked, _orbits, _to_grid
from puzzledesk.core.lexicon import MultiLexicon
from puzzledesk.core.rng import Rng, RngFactory

# Annealing defaults: a short geometric schedule from a warm start to a near-greedy
# tail is enough for a <=15x15 field (measured -- see scripts/gibbs.py / notes.md).
DEFAULT_SWEEPS = 60
DEFAULT_T0 = 1.5
DEFAULT_T1 = 0.06
# Attempts per generated layout before a draw is abandoned. A disconnected or
# still-illegal anneal is rejected (connectivity is global; see module docstring), so a
# few restarts per yielded grid absorb the reject rate without ever calling a miss a proof.
DEFAULT_ATTEMPTS = 40


@dataclass(frozen=True, slots=True)
class FieldParams:
    """The energy's local factors and their weights -- the whole model.

    Legality (``w_legal``, ``w_2x2``) is weighted well above the soft aesthetic terms
    (``w_density``, ``w_cluster``) so the anneal settles into a legal basin first and
    *then* trades off density against spread within it. ``target_black`` is the density
    the field is pulled toward (an exact-count spring, not a hard ceiling); ``max_len``
    caps entry length as in ``gen_capped``. Tunable knobs, not constants -- the
    benchmark (scripts/gibbs.py) is what set the defaults.
    """

    min_len: int = 3
    max_len: int | None = None
    target_black: int = 0
    w_legal: float = 8.0  # run-length legality (dominant; keeps samples legal)
    w_2x2: float = 5.0  # forbid a 2x2 all-black block (the American-grid rule)
    w_density: float = 0.20  # (n_black - target)^2 spring toward the target count
    w_cluster: float = 0.55  # anti-cluster: penalty per 4-adjacent black-black pair

    @classmethod
    def from_fraction(
        cls,
        rows: int,
        cols: int,
        *,
        black_fraction: float = 0.16,
        min_len: int = 3,
        max_len: int | None = None,
    ) -> FieldParams:
        """Build the field with its density *target* derived from a black-cell fraction of
        the grid -- the ergonomic path for "make ~16% of the cells black" when the caller
        has a fraction rather than an exact count. The one place the field is specified is
        still this value; the samplers take a ``FieldParams``, not loose density kwargs (D43)."""
        return cls(
            min_len=min_len, max_len=max_len, target_black=round(black_fraction * rows * cols)
        )


@dataclass(frozen=True, slots=True)
class AnnealSchedule:
    """The geometric temperature schedule for one anneal: ``sweeps`` random-order Gibbs
    passes cooling from ``t0`` to ``t1`` (D42). Bundled so the four anneal functions --
    and the sampler *twin* ``gibbs_layouts``/``fill_gibbs`` -- pass one value instead of
    re-listing the same three knobs. Defaults are the benchmarked schedule
    (:data:`DEFAULT_SWEEPS`/:data:`DEFAULT_T0`/:data:`DEFAULT_T1`, set by scripts/gibbs.py)."""

    sweeps: int = DEFAULT_SWEEPS
    t0: float = DEFAULT_T0
    t1: float = DEFAULT_T1


# A shared, immutable default (a frozen instance is safe to share) -- avoids a call in an
# argument default (flake8-bugbear B008) while keeping the benchmarked schedule the
# zero-config path.
_DEFAULT_SCHEDULE = AnnealSchedule()


@dataclass(frozen=True, slots=True)
class SampleBudget:
    """The bounds that make :func:`fill_gibbs` a *sampler*, not a proof -- the Gibbs-side
    analogue of :class:`patterns.SearchBudget` (D43). ``attempts_per_layout`` retries one
    yield past illegal/disconnected anneals; ``max_layouts`` caps how many sampled layouts
    are tried; ``fill_nodes`` bounds each fill's search tree. Every field is a budget, so a
    ``None`` from ``fill_gibbs`` is *always* exhaustion, never a UNSAT theorem (that is what
    ``patterns.fill_capped`` is for)."""

    attempts_per_layout: int = DEFAULT_ATTEMPTS
    max_layouts: int = 40
    fill_nodes: int | None = None


_DEFAULT_SAMPLE_BUDGET = SampleBudget()


def _line_penalty(line: list[bool], min_len: int, max_len: int | None) -> int:
    """Count the illegal white runs in one row/column: a run of length 1..min_len-1
    (too short / unchecked) or, if capped, a run longer than max_len."""
    bad = 0
    run = 0
    for black in (*line, True):  # sentinel closes the final open run
        if not black:
            run += 1
            continue
        if 0 < run < min_len:
            bad += 1
        if max_len is not None and run > max_len:
            bad += 1
        run = 0
    return bad


def _lines_energy(
    grid: list[list[bool]],
    rows: int,
    cols: int,
    aff_rows: set[int],
    aff_cols: set[int],
    p: FieldParams,
) -> float:
    """Legality energy of just the affected rows/columns. In a single Gibbs step only
    the orbit's rows and columns change run structure, so this is the whole delta on the
    legality term (everything else is identical between the black/white configs and
    cancels)."""
    bad = 0
    for r in aff_rows:
        bad += _line_penalty([grid[r][c] for c in range(cols)], p.min_len, p.max_len)
    for c in aff_cols:
        bad += _line_penalty([grid[r][c] for r in range(rows)], p.min_len, p.max_len)
    return p.w_legal * bad


def _cluster_touch(
    grid: list[list[bool]], rows: int, cols: int, orbit: list[tuple[int, int]], p: FieldParams
) -> float:
    """Cluster energy (adjacent black-black pairs + 2x2 black blocks) *touching* the
    orbit cells. Only terms incident to a changed cell differ between the two configs, so
    this local sum is the whole cluster delta. With the orbit white it is 0 (no black-black
    term can include a white cell), which is exactly right: whitening the orbit removes
    every cluster penalty it carried."""
    e = 0.0
    seen_pairs: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    seen_blocks: set[tuple[int, int]] = set()
    for r, c in orbit:
        if not grid[r][c]:
            continue
        for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc]:
                key = ((r, c), (nr, nc)) if (r, c) < (nr, nc) else ((nr, nc), (r, c))
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    e += p.w_cluster
        for tr in (r - 1, r):
            for tc in (c - 1, c):
                if not (tr >= 0 and tr + 1 < rows and tc >= 0 and tc + 1 < cols):
                    continue
                full = (
                    grid[tr][tc] and grid[tr + 1][tc] and grid[tr][tc + 1] and grid[tr + 1][tc + 1]
                )
                if full and (tr, tc) not in seen_blocks:
                    seen_blocks.add((tr, tc))
                    e += p.w_2x2
    return e


def _black_prob(
    grid: list[list[bool]],
    rows: int,
    cols: int,
    orbit: list[tuple[int, int]],
    base_nb: int,
    p: FieldParams,
    temp: float,
) -> float:
    """The Gibbs conditional ``P(orbit black | rest)`` at temperature ``temp``.

    Evaluates the energy delta between colouring the whole orbit black vs white, using
    only the local (affected-line + touching-cluster) terms plus the global density
    spring. ``base_nb`` is the black count with this orbit *excluded*. Mutates ``grid``
    while probing and leaves the orbit **white** on return (the caller sets the drawn
    colour). Numerically stable sigmoid.
    """
    k = len(orbit)
    aff_rows = {r for r, _ in orbit}
    aff_cols = {c for _, c in orbit}

    for r, c in orbit:
        grid[r][c] = True
    e_black = (
        _lines_energy(grid, rows, cols, aff_rows, aff_cols, p)
        + _cluster_touch(grid, rows, cols, orbit, p)
        + p.w_density * (base_nb + k - p.target_black) ** 2
    )
    for r, c in orbit:
        grid[r][c] = False
    e_white = (
        _lines_energy(grid, rows, cols, aff_rows, aff_cols, p)
        + _cluster_touch(grid, rows, cols, orbit, p)
        + p.w_density * (base_nb - p.target_black) ** 2
    )

    logit = (e_white - e_black) / temp
    if logit >= 0:
        return 1.0 / (1.0 + math.exp(-logit))
    ex = math.exp(logit)
    return ex / (1.0 + ex)


def _reps(rows: int, cols: int, symmetric: bool) -> list[list[tuple[int, int]]]:
    """The units the sampler colours atomically: 180°-rotation orbits when symmetric
    (so every sample is symmetric by construction), else one cell each."""
    if symmetric:
        return _orbits(rows, cols)
    return [[(r, c)] for r in range(rows) for c in range(cols)]


def _max_run_ok(line: list[bool], max_len: int) -> bool:
    """True iff no white run in this row/column exceeds ``max_len``."""
    run = 0
    for black in (*line, True):
        if black:
            run = 0
        else:
            run += 1
            if run > max_len:
                return False
    return True


def _cap_ok(grid: list[list[bool]], rows: int, cols: int, max_len: int | None) -> bool:
    """True iff every white run (both directions) is within the cap. Once
    :func:`_fully_checked` holds (no run in 1..min_len-1), this is exactly the slot cap --
    so it replaces the slower build-the-grid-and-scan-slots check."""
    if max_len is None:
        return True
    if any(not _max_run_ok([grid[r][c] for c in range(cols)], max_len) for r in range(rows)):
        return False
    return all(_max_run_ok([grid[r][c] for r in range(rows)], max_len) for c in range(cols))


def _finalize(grid: list[list[bool]], rows: int, cols: int, p: FieldParams) -> BlockedGrid | None:
    """Gate an annealed field to a legal :class:`BlockedGrid`, or ``None``.

    Legality is exactly ``gen_capped``'s: fully checked (no white run in 1..min_len-1,
    both directions -- ``patterns._fully_checked``), every entry within ``max_len``
    (``_cap_ok``), and the white cells 4-connected (``patterns._connected`` -- the one
    global constraint the field energy cannot carry, so it is a plain reject here). Reusing
    ``patterns``' predicates means a yielded grid is legal by the *same* definition the
    complete search guarantees.

    Disconnection is a *reject*, not a repair: a D28 spike whitened "bridge" blacks to
    reconnect, but under a length cap the separating blacks are cap-load-bearing, so
    whitening re-creates an over-cap run -- it fixed ~0 and was removed (see D28).
    """
    nb = sum(grid[r][c] for r in range(rows) for c in range(cols))
    if nb == 0 or nb == rows * cols:
        return None  # a fully white/black grid is not a puzzle
    if not _fully_checked(grid, rows, cols, p.min_len):
        return None
    if not _cap_ok(grid, rows, cols, p.max_len):
        return None
    if not _connected(grid, rows, cols, rows * cols - nb):
        return None
    return _to_grid(grid, rows, cols, p.min_len)


def anneal_field(
    rows: int,
    cols: int,
    *,
    rng: Rng,
    params: FieldParams,
    symmetric: bool = True,
    schedule: AnnealSchedule = _DEFAULT_SCHEDULE,
) -> list[list[bool]]:
    """Run the annealed-Gibbs sweep and return the *raw* binary field (before the legality
    gate). Split out of :func:`sample_layout` so a study can classify what the anneal
    produced (:func:`reject_reason`) without re-implementing the loop. The temperature falls
    geometrically from ``t0`` to ``t1`` over ``schedule.sweeps`` sweeps, each a random-order
    pass of Gibbs updates over the 180°-rotation orbits (so every field is symmetric)."""
    sweeps, t0, t1 = schedule.sweeps, schedule.t0, schedule.t1
    reps = _reps(rows, cols, symmetric)
    frac = params.target_black / (rows * cols)
    grid = [[False] * cols for _ in range(rows)]
    nb = 0
    # Warm start near the target density so the anneal has less distance to travel.
    for orbit in reps:
        if rng.random() < frac:
            for r, c in orbit:
                grid[r][c] = True
            nb += len(orbit)

    order = list(range(len(reps)))
    for s in range(sweeps):
        temp = t0 * (t1 / t0) ** (s / (sweeps - 1)) if sweeps > 1 else t1
        rng.shuffle(order)
        for i in order:
            orbit = reps[i]
            r0, c0 = orbit[0]
            cur_black = grid[r0][c0]
            base_nb = nb - (len(orbit) if cur_black else 0)
            pblack = _black_prob(grid, rows, cols, orbit, base_nb, params, temp)
            make_black = rng.random() < pblack  # _black_prob left the orbit white
            if make_black:
                for r, c in orbit:
                    grid[r][c] = True
            nb = base_nb + (len(orbit) if make_black else 0)
    return grid


def reject_reason(grid: list[list[bool]], rows: int, cols: int, p: FieldParams) -> str:
    """Why :func:`_finalize` would reject (or accept) this raw field: one of
    ``ok`` / ``degenerate`` / ``short_run`` / ``over_cap`` / ``disconnected`` -- the study
    instrument that reveals how the sampler's failure mode shifts with basin shape and
    count (D28). Same predicate order as :func:`_finalize`."""
    nb = sum(grid[r][c] for r in range(rows) for c in range(cols))
    if nb == 0 or nb == rows * cols:
        return "degenerate"
    if not _fully_checked(grid, rows, cols, p.min_len):
        return "short_run"
    if not _cap_ok(grid, rows, cols, p.max_len):
        return "over_cap"
    if not _connected(grid, rows, cols, rows * cols - nb):
        return "disconnected"
    return "ok"


def sample_layout(
    rows: int,
    cols: int,
    *,
    rng: Rng,
    params: FieldParams,
    symmetric: bool = True,
    schedule: AnnealSchedule = _DEFAULT_SCHEDULE,
) -> BlockedGrid | None:
    """One annealed-Gibbs draw over the black-cell field.

    Returns a legal, connected, (optionally) symmetric :class:`BlockedGrid`, or ``None`` if
    this single anneal came out illegal/disconnected. Symmetry is by construction (orbit
    colouring); connectivity is a plain reject in :func:`_finalize` (D28 showed a repair is
    defeated by the cap).
    """
    grid = anneal_field(rows, cols, rng=rng, params=params, symmetric=symmetric, schedule=schedule)
    return _finalize(grid, rows, cols, params)


def gibbs_layouts(
    rows: int,
    cols: int,
    *,
    rng: Rng,
    params: FieldParams,
    symmetric: bool = True,
    schedule: AnnealSchedule = _DEFAULT_SCHEDULE,
    attempts_per_layout: int = DEFAULT_ATTEMPTS,
) -> Iterator[BlockedGrid]:
    """Yield legal length-capped layouts, sampled from the energy field -- the
    sampler-side analogue of :func:`patterns.gen_capped`.

    The whole field -- length window, density target, weights -- is the ``params``
    :class:`FieldParams` (build one from a fraction with :meth:`FieldParams.from_fraction`).
    Each yielded grid is one *successful* anneal; up to ``attempts_per_layout`` draws are
    tried per yield to absorb the reject rate (illegal or disconnected anneals).

    **Not a proof.** Unlike ``gen_capped``, exhausting this generator (it stops after a
    yield fails ``attempts_per_layout`` times) is **budget exhaustion, never UNSAT** --
    it is a sampler. Use ``patterns.capped_layout_exists`` for the existence theorem.
    ``rng`` is consumed deterministically, so a given ``(seed)`` stream reproduces the
    same sequence of layouts.
    """
    while True:
        got: BlockedGrid | None = None
        for _ in range(attempts_per_layout):
            g = sample_layout(
                rows, cols, rng=rng, params=params, symmetric=symmetric, schedule=schedule
            )
            if g is not None:
                got = g
                break
        if got is None:
            return  # budget of attempts spent for this yield -- exhaustion, not a proof
        yield got


def fill_gibbs(
    rows: int,
    cols: int,
    mlex: MultiLexicon,
    *,
    rng_factory: RngFactory,
    params: FieldParams,
    seed: int = 0,
    symmetric: bool = True,
    distinct: bool = True,
    schedule: AnnealSchedule = _DEFAULT_SCHEDULE,
    budget: SampleBudget = _DEFAULT_SAMPLE_BUDGET,
) -> tuple[BlockedGrid, dict[int, str]] | None:
    """Sample energy-field layouts and fill the first that admits a distinct fill --
    the *sampler* analogue of :func:`patterns.fill_capped`.

    Same shape and return as ``fill_capped``: ``(grid, assign)`` or ``None``. The
    difference is only the layout source -- :func:`gibbs_layouts` (annealed Gibbs over
    the black-cell field, aesthetic-controlled: density, spread, no 2x2 block) instead
    of the complete cap-driven search. The field is the ``params`` :class:`FieldParams`;
    the sampler bounds are one :class:`SampleBudget`. ``budget.max_layouts`` caps how many
    sampled layouts are tried (the generator is otherwise unbounded); a ``None`` here is
    **budget exhaustion, never a proof** -- both the layout source *and* every ``budget``
    field are samplers (use ``patterns.fill_capped`` for the completeness of the layout
    search). The layout stream and every fill re-seed from ``rng_factory.create(seed)``.
    """
    layouts = gibbs_layouts(
        rows,
        cols,
        rng=rng_factory.create(seed),
        params=params,
        symmetric=symmetric,
        schedule=schedule,
        attempts_per_layout=budget.attempts_per_layout,
    )
    for tried, g in enumerate(layouts):
        if tried >= budget.max_layouts:
            return None
        assign = fill.solve(
            g, mlex, rng=rng_factory.create(seed), distinct=distinct, node_budget=budget.fill_nodes
        )
        if assign is not None:
            return g, assign
    return None
