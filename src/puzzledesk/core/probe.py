"""The observation port: how a running engine exposes its own workings.

The engines are tight, complete backtracking loops that can run for a while on a big
grid. "Is it progressing, or stuck?" wants a window into the search *without changing
it* -- the mirror image of the rng port. Where :mod:`puzzledesk.core.rng` is the one
impure *input* (randomness flows in), ``Probe`` is the one observation *output*
(structured events flow out), and it is held to the same discipline:

  * **Observe-only.** A probe may read what the engine reports; it can never see the
    ``rng`` or steer the search. Determinism and completeness -- the load-bearing "a
    ``None`` is a proof" -- must not depend on whether anyone is watching.
  * **Free by default.** The default :data:`NULL_PROBE` is a genuine no-op, and the hot
    loops only *build* an event every :data:`PROGRESS_STRIDE` nodes, so an un-watched
    search runs at its old speed and the benchmarks in ``docs/notes.md`` stay honest.
  * **Its own vocabulary.** :data:`Event` is a small closed union of plain records, no
    third-party types. Logs, a live heartbeat, an SSE stream, a metrics sink, a test
    recorder are all *adapters* behind this one port -- "logging" is just the adapter
    that formats an event as a line, and a backend like OpenTelemetry maps these onto
    spans in an adapter (the kernel never imports it -- D18's ``forbidden`` contract).

Granularity is the whole game: **push milestones, sample rates.** Rare, meaningful
events (:class:`Attempt`, :class:`Solved`, :class:`Finished`) are emitted as they
happen; the per-node firehose is instead a counter the engine snapshots every
:data:`PROGRESS_STRIDE` nodes (:class:`Progress`). Never one event per node -- that
would change the very thing it measures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# Search-tree nodes between Progress snapshots. A power of two so the hot-loop gate is
# a cheap ``nodes % PROGRESS_STRIDE`` (and large enough that building the odd event is
# lost in the noise of the search).
PROGRESS_STRIDE = 4096


@dataclass(frozen=True, slots=True)
class PhaseStarted:
    """A named stage of a run began -- e.g. the layout search, or the fill."""

    phase: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Attempt:
    """The fill engine was handed the ``n``-th candidate layout (0-based): a grid with
    ``black`` black cells and ``slots`` entries to fill."""

    n: int
    black: int
    slots: int


@dataclass(frozen=True, slots=True)
class Progress:
    """A sampled snapshot of a search in flight (every :data:`PROGRESS_STRIDE` nodes).
    ``nodes`` is tree nodes visited in this ``phase``; ``depth`` is how far the current
    partial reaches (filled slots, or placed rows)."""

    phase: str
    nodes: int
    depth: int


@dataclass(frozen=True, slots=True)
class Solved:
    """A phase produced a result -- a layout that filled -- after ``nodes`` nodes."""

    phase: str
    nodes: int


@dataclass(frozen=True, slots=True)
class Finished:
    """A composite run ended. ``ok`` is whether it produced a grid; ``reason`` is
    ``"solved"``, ``"exhausted"`` (a *complete* search ran dry -- a real UNSAT proof),
    or ``"budget"`` (a bounded search merely ran out -- not a proof). ``attempts`` is
    how many candidate layouts were tried. The epistemic tag the engines already carry,
    surfaced on the wire."""

    ok: bool
    reason: str
    attempts: int


# The closed union. Consumers ``match`` on it (and get ``assert_never`` exhaustiveness);
# adding a variant is a deliberate change every adapter sees.
Event = PhaseStarted | Attempt | Progress | Solved | Finished


@runtime_checkable
class Probe(Protocol):
    """The observation port. One method -- receive a structured :data:`Event` -- so a
    new event variant never grows the port's surface; adapters decide what an event
    *means* (a log line, a heartbeat frame, an SSE message, a metric, an assertion)."""

    def emit(self, event: Event) -> None: ...


class NullProbe:
    """The default: watching nothing costs nothing. ``emit`` is a no-op, so an engine
    can call it unconditionally at milestone points and gate only the per-node
    :class:`Progress` behind the stride check."""

    def emit(self, event: Event) -> None:
        return None


# A shared stateless singleton -- used as the engines' default ``probe=`` so the
# uninstrumented call is free and needs no ``None`` check (and no B008 default-call).
NULL_PROBE = NullProbe()
