"""The `core.probe.Probe` *adapters* (adapters/probe.py), as unit tests.

These pin how each adapter *renders* the engines' structured events -- the effect
side the kernel is forbidden. They are pure DI unit tests, not integration: the
``write`` sink and (for the heartbeat) the wall clock are injected fakes
(``RecordingWriter``/``FakeClock``), so nothing runs an engine, touches a stream, or
reads the real clock. An event record goes in; the rendered string is asserted.

The contracts that matter here:

  * ``LoggingProbe`` maps every ``Event`` variant to one line, and the ``ok``/reason
    split on ``Finished`` is surfaced verbatim (the epistemic tag reaches the log);
  * ``HeartbeatProbe`` repaints a single in-place line (``\\r``, no newline) for the
    live events and computes elapsed/rate from the *injected* clock, so the numbers are
    deterministic; ``Attempt`` restarts the per-fill node count; ``Finished`` closes the
    line with a newline.
"""

from __future__ import annotations

from fakes import FakeClock, RecordingWriter

from puzzledesk.adapters.probe import HeartbeatProbe, LoggingProbe
from puzzledesk.core.probe import Attempt, Finished, PhaseStarted, Progress, Solved

# --- LoggingProbe: one line per event ------------------------------------------------


def test_logging_renders_each_event_as_a_line() -> None:
    w = RecordingWriter()
    probe = LoggingProbe(w)
    probe.emit(PhaseStarted("capped", "10x10 cap<=5"))
    probe.emit(Attempt(0, 18, 24))
    probe.emit(Progress("fill", 8192, 3))
    probe.emit(Solved("fill", 12345))
    assert w.lines == [
        "[capped] start 10x10 cap<=5",
        "[capped] attempt #0 - 18 black, 24 slots",
        "[fill] 8,192 nodes (depth 3)",
        "[fill] filled after 12,345 nodes",
    ]


def test_logging_phase_started_without_detail_is_rstripped() -> None:
    # An empty detail must not leave a trailing space (the .rstrip() in the renderer).
    w = RecordingWriter()
    LoggingProbe(w).emit(PhaseStarted("layout"))
    assert w.lines == ["[layout] start"]


def test_logging_finished_surfaces_the_ok_reason_split() -> None:
    # The epistemic tag reaches the log verbatim: a solve says "solved"; an unsolved run
    # shows its reason (exhausted = a proof, budget = not one), never a generic failure.
    solved, exhausted, budget = RecordingWriter(), RecordingWriter(), RecordingWriter()
    LoggingProbe(solved).emit(Finished(ok=True, reason="solved", attempts=3))
    LoggingProbe(exhausted).emit(Finished(ok=False, reason="exhausted", attempts=0))
    LoggingProbe(budget).emit(Finished(ok=False, reason="budget", attempts=40))
    assert solved.lines == ["[done] solved - 3 layout(s) tried"]
    assert exhausted.lines == ["[done] exhausted - 0 layout(s) tried"]
    assert budget.lines == ["[done] budget - 40 layout(s) tried"]


def test_logging_defaults_to_print() -> None:
    # The default sink is print (an adapter's choice, not the kernel's) -- constructing
    # with no writer must not raise, and emitting goes somewhere harmless.
    LoggingProbe().emit(PhaseStarted("x"))  # no assertion: just that the default wiring works


# --- HeartbeatProbe: an in-place line, elapsed/rate from the injected clock -----------


def test_heartbeat_repaints_in_place_with_clock_driven_rate() -> None:
    clock = FakeClock(100.0)
    w = RecordingWriter()
    probe = HeartbeatProbe(w, now=clock)  # start = 100.0
    clock.t = 102.0  # 2s elapsed
    probe.emit(Progress("fill", 8192, 3))
    (line,) = w.lines
    assert line.startswith("\r")  # in-place repaint, not a new line
    assert not line.endswith("\n")
    assert "fill" in line
    assert "8,192 nodes" in line
    assert "4,096/s" in line  # 8192 nodes / 2s
    assert "2.0s" in line


def test_heartbeat_attempt_resets_the_node_count() -> None:
    # A new candidate layout's fill starts its node count over, so the rate reflects the
    # current fill, not the cumulative total.
    clock = FakeClock(0.0)
    w = RecordingWriter()
    probe = HeartbeatProbe(w, now=clock)
    clock.t = 1.0
    probe.emit(Progress("fill", 9999, 5))
    clock.t = 2.0
    probe.emit(Attempt(1, 20, 30))  # resets nodes -> 0
    assert w.lines[-1].split("nodes")[0].strip().endswith("0")
    assert "attempt   2" in w.lines[-1]  # n + 1, right-aligned width 3


def test_heartbeat_finished_closes_the_line_with_a_newline() -> None:
    clock = FakeClock(10.0)
    w = RecordingWriter()
    probe = HeartbeatProbe(w, now=clock)
    clock.t = 13.5
    probe.emit(Solved("fill", 500))  # sets the node count shown on the terminal line
    probe.emit(Finished(ok=False, reason="budget", attempts=40))
    done = w.lines[-1]
    assert done.startswith("\r") and done.endswith("\n")
    assert "BUDGET" in done  # reason upper-cased on the terminal line
    assert "40 attempt(s)" in done
    assert "500 nodes" in done
    assert "3.5s" in done


def test_heartbeat_paint_never_divides_by_zero_at_t0() -> None:
    # First paint can happen at elapsed == 0 (same clock reading as start); the adapter
    # floors elapsed so the rate is finite, not a ZeroDivisionError.
    clock = FakeClock(5.0)
    w = RecordingWriter()
    probe = HeartbeatProbe(w, now=clock)  # start == now == 5.0
    probe.emit(PhaseStarted("layout"))  # elapsed 0 -> must not raise
    assert w.lines and w.lines[0].startswith("\r")
