"""Adapters behind the :class:`~puzzledesk.core.probe.Probe` port.

The kernel emits structured events (``core.probe``); *what an event means* is an
adapter's job, and this is where the effects (I/O, the wall clock) live -- never in
``core``. Two here, both driving the same events:

  * :class:`LoggingProbe` -- the "old-school" rendering: format each event as a line.
    Included precisely to make the point that logging is just *one* consumer of the
    event stream, not a separate mechanism.
  * :class:`HeartbeatProbe` -- a live, single-line progress readout for a long run:
    attempts tried, nodes explored, nodes/sec, elapsed, redrawn in place. This is the
    "is it alive and roughly how far?" signal a big-grid generation wants.

Both take a ``write`` sink (any ``str -> None``) so the composition root chooses the
stream (stderr for a tool, an SSE queue for the web front). The wall clock lives here,
in an adapter, because ``core`` is forbidden it (determinism; D18).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import assert_never

from puzzledesk.core.probe import (
    Attempt,
    Event,
    Finished,
    PhaseStarted,
    Progress,
    Solved,
)


class LoggingProbe:
    """Render each event as a line via ``write`` (default: ``print``). Logging as an
    adapter -- one rendering of the event stream among many."""

    def __init__(self, write: Callable[[str], None] = print) -> None:
        self._write = write

    def emit(self, event: Event) -> None:
        match event:
            case PhaseStarted(phase, detail):
                self._write(f"[{phase}] start {detail}".rstrip())
            case Attempt(n, black, slots):
                self._write(f"[capped] attempt #{n} - {black} black, {slots} slots")
            case Progress(phase, nodes, depth):
                self._write(f"[{phase}] {nodes:,} nodes (depth {depth})")
            case Solved(phase, nodes):
                self._write(f"[{phase}] filled after {nodes:,} nodes")
            case Finished(ok, reason, attempts):
                verdict = "solved" if ok else reason
                self._write(f"[done] {verdict} - {attempts} layout(s) tried")
            case _ as unreachable:
                assert_never(unreachable)


class HeartbeatProbe:
    """A live, in-place progress line for a long run. Accumulates the sampled counters
    and repaints a single status line (carriage-return, no newline) so a big-grid
    generation shows it is alive and roughly how far along it is.

    ``now`` is injected (default ``time.monotonic``) so a test can drive it with a fake
    clock; the wall clock is confined to this adapter, never the kernel."""

    def __init__(
        self,
        write: Callable[[str], None],
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._write = write
        self._now = now
        self._start = now()
        self._attempts = 0
        self._phase = ""
        self._nodes = 0

    def _paint(self) -> None:
        elapsed = max(self._now() - self._start, 1e-9)
        rate = self._nodes / elapsed
        self._write(
            f"\r  {self._phase:<6} {self._nodes:>12,} nodes  "
            f"{rate:>10,.0f}/s  attempt {self._attempts:>3}  {elapsed:6.1f}s "
        )

    def emit(self, event: Event) -> None:
        match event:
            case PhaseStarted(phase, _):
                self._phase = phase
                self._paint()
            case Attempt(n, _, _):
                self._attempts = n + 1
                self._nodes = 0  # a fresh fill's node count starts over
                self._paint()
            case Progress(phase, nodes, _):
                self._phase = phase
                self._nodes = nodes
                self._paint()
            case Solved(_, nodes):
                self._nodes = nodes
                self._paint()
            case Finished(ok, reason, attempts):
                verdict = "solved" if ok else reason.upper()
                elapsed = self._now() - self._start
                self._write(
                    f"\r  done: {verdict} after {attempts} attempt(s), "
                    f"{self._nodes:,} nodes, {elapsed:.1f}s" + " " * 20 + "\n"
                )
            case _ as unreachable:
                assert_never(unreachable)
