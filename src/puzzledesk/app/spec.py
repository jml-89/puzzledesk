"""Generation specs -- the formal, typed request objects a caller (a CLI, and soon a
REST API) hands the generator instead of a bucket of loose keyword arguments.

The design rule is D15's, now applied to generation input: *introduce a modelled
structure only where an external contract forces it.* argparse never forced it (named
flags are free), so the services grew flat, overlapping kwarg lists -- one method per
layout engine, each with its own subset of knobs (``fill_once`` / ``fill_capped_once``
/ ``fill_capped_gibbs_once``). A serialized API body *does* force it: the request must
be one validatable object. So we model it, and the internal call sites get the same
clarity for free.

Three pieces plus the aggregate:

  * :class:`GridSpec` -- the shape + quality band + seed every strategy shares.
  * :data:`LayoutStrategy` -- a **closed, tagged union** of one frozen record per
    layout engine, each carrying *only its own* knobs. The illegal combinations the
    flat kwargs allowed (``max_black`` on the Gibbs field, ``max_layouts`` on the
    complete count search) are now *unrepresentable*. And the epistemic tag the whole
    design rests on -- is a ``None`` a UNSAT **proof** or mere budget exhaustion? --
    becomes a property of the variant (:func:`layout_is_complete`) instead of lore
    buried in a method name.
  * :class:`FillSpec` -- the word-assignment *selection* knobs (difficulty targeting,
    D23). Distinctness (invariant 3) is not a knob; it is always on.
  * :class:`PuzzleSpec` -- the whole-puzzle aggregate: grid + layout + fill + clue.
    The one object the puzzle use-case (and the API) takes.

These are pure ``app``-layer value objects, exactly like :class:`ClueStyle`; the wire
format an API speaks is a *separate* schema that parses into these (the D15 rule again:
the port speaks the canonical form, the serialization is an export concern).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NoReturn

from puzzledesk.app.clue import ClueStyle


def assert_never(value: NoReturn) -> NoReturn:
    """Exhaustiveness guard for a ``match`` over a closed union: reaching it is a type
    error mypy catches (the parameter is ``NoReturn``), so adding a new
    :data:`LayoutStrategy` variant fails the type check at every dispatch until handled.

    Hand-rolled rather than imported from ``typing`` on purpose: ``typing.assert_never``
    is 3.11+, and the project floor is a hard 3.10 (CLAUDE.md, "Modern Python -- with one
    hard boundary"). The ``NoReturn`` idiom gives the identical static check on 3.10.
    """
    raise AssertionError(f"unhandled case: {value!r}")


@dataclass(frozen=True, slots=True)
class GridSpec:
    """What every layout strategy shares: the grid shape, the quality band the words
    are drawn from, and the seed that makes a run reproducible.

    ``max_score=None`` is a plain quality *floor*; a finite ``max_score`` turns it into a
    two-sided obscurity *band* -- the difficulty knob (D21). ``seed`` reproduces a fill
    exactly (a ``(lists, spec, seed)`` triple is deterministic for the complete engines).
    """

    rows: int = 5
    cols: int = 5
    min_score: float = 75.0
    max_score: float | None = None
    seed: int = 0


@dataclass(frozen=True, slots=True)
class FullSquare:
    """The fully-checked square (no black cells): the ``DoubleSquare`` model, where the
    down words are *induced* by reading columns (invariant 1). Requires ``rows == cols``.
    The search is **complete**, so a ``None`` fill is a genuine UNSAT proof."""


@dataclass(frozen=True, slots=True)
class CountLayout:
    """A blocked layout from an exact black-cell *count* (D13). The layout search is
    **complete**: a ``None`` (no legal count-``num_black`` layout fills from these lists)
    is a UNSAT theorem, not a timeout."""

    num_black: int = 4
    symmetric: bool = True
    min_len: int = 3


@dataclass(frozen=True, slots=True)
class CappedLayout:
    """A blocked layout that caps every entry's *length* (D24), so a grid larger than the
    word data still fills. ``num_black`` pins the count exactly; ``max_black`` bounds it
    above; with neither, the service defaults to a sensible black ceiling (D25). The
    search is complete but **always budgeted** here (``max_patterns`` / an internal node
    budget), so a ``None`` is budget exhaustion, *not* a UNSAT proof -- use
    :meth:`~puzzledesk.app.generate.GenerateService.layout_exists` for the existence
    theorem."""

    max_len: int
    num_black: int | None = None
    max_black: int | None = None
    symmetric: bool = True
    min_len: int = 3
    max_patterns: int | None = None


@dataclass(frozen=True, slots=True)
class GibbsLayout:
    """A blocked layout drawn from the Gibbs energy field (D27): aesthetic-controlled
    density/spread and a guaranteed no-2x2-black-block texture. A **sampler**, so a
    ``None`` is budget exhaustion (no sampled layout filled within ``max_layouts``),
    never a proof -- more so than :class:`CappedLayout`. ``num_black`` sets an exact-count
    spring; unset, density defaults to a black fraction of the cells."""

    max_len: int
    num_black: int | None = None
    symmetric: bool = True
    min_len: int = 3
    max_layouts: int = 40


#: The closed set of layout strategies. Dispatch over it with ``match`` +
#: :func:`assert_never` so a new engine is a compile-time obligation at every call site.
LayoutStrategy = FullSquare | CountLayout | CappedLayout | GibbsLayout


def layout_is_complete(layout: LayoutStrategy) -> bool:
    """Whether a ``None`` from this strategy is a **UNSAT proof** (a complete search
    exhausted the tree) or mere **budget exhaustion** (a budgeted/sampled search gave up).
    This is the load-bearing epistemic distinction (architecture.md, "None is a proof"),
    now carried by the type rather than by which method the caller happened to reach for
    -- so a caller (e.g. the API's "no puzzle" response) can word it honestly from the tag.
    """
    match layout:
        case FullSquare() | CountLayout():
            return True
        case CappedLayout() | GibbsLayout():
            return False
    assert_never(layout)


@dataclass(frozen=True, slots=True)
class FillSpec:
    """The word-assignment *selection* knobs, distinct from the layout search.

    ``min_hard_gets > 0`` *targets a difficulty* (D23): keep only grids the solve-order
    model says need at least that many hard gets, read under clue-difficulty ``gimme``.
    Selection is best-of-a-seed-budget over a soft score -- **not** a proof (unlike the
    layout ``None``). Distinctness (invariant 3) is not here: it is always enforced.
    """

    min_hard_gets: int = 0
    gimme: float = 80.0


@dataclass(frozen=True, slots=True)
class PuzzleSpec:
    """The whole-puzzle request aggregate: the shape/quality (:class:`GridSpec`), the
    layout engine and its tuning (:data:`LayoutStrategy`), the fill selection
    (:class:`FillSpec`), and the clue style (:class:`ClueStyle`). The one object the
    end-to-end puzzle use-case takes -- and the shape a REST body parses into.

    ``fill`` is threaded to the square/difficulty path; blocked difficulty targeting is a
    later step, so on the blocked layouts it is presently reserved (carried, not applied).
    """

    grid: GridSpec = field(default_factory=GridSpec)
    layout: LayoutStrategy = field(default_factory=CountLayout)
    fill: FillSpec = field(default_factory=FillSpec)
    clue: ClueStyle = field(default_factory=ClueStyle)
