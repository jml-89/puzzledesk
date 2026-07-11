"""Demo the observation port (core.probe): watch a big-grid generation run.

Generation on a large capped grid is a long, silent backtracking search -- the case that
motivated the port. This driver attaches a probe and shows the two adapter renderings of
the identical event stream, then the epistemic tag the port carries out.

  1. LoggingProbe   -- every event as a line ("logging is just one consumer");
  2. HeartbeatProbe -- one live progress line (attempts / nodes / nodes-per-sec / elapsed);
  3. the proof-vs-budget tag -- a *complete* search that finds nothing reports
     ``exhausted`` (a real UNSAT theorem); a *bounded* one reports ``budget``.

The probe is observe-only: attaching it does not change the grid found (there is a test
for exactly that, tests/test_probe.py::test_probe_does_not_change_result).

    uv run scripts/spike_probe.py            # the tuned demo
    uv run scripts/spike_probe.py 12 12 5 66 1 10000   # rows cols max_len floor seed fill-budget
"""
from __future__ import annotations

import sys

from puzzledesk.adapters.probe import HeartbeatProbe, LoggingProbe
from puzzledesk.app.puzzle import filled_from_blocked
from puzzledesk.bootstrap import build
from puzzledesk.core.engines import patterns

C = build()


def fill(rows, cols, max_len, floor, seed, *, probe, node_budget=None, max_patterns=None,
         num_black=None):
    mlex = C.lexicon.load_multi("cw", range(3, max_len + 1), min_score=floor)
    return patterns.fill_capped(
        rows, cols, mlex, rng_factory=C.rng_factory, max_len=max_len, seed=seed,
        min_len=3, symmetric=True, distinct=True, num_black=num_black,
        node_budget=node_budget, max_patterns=max_patterns, probe=probe,
    )


def main() -> None:
    a = sys.argv[1:]
    rows = int(a[0]) if len(a) > 0 else 12
    cols = int(a[1]) if len(a) > 1 else 12
    max_len = int(a[2]) if len(a) > 2 else 5
    floor = int(a[3]) if len(a) > 3 else 66
    seed = int(a[4]) if len(a) > 4 else 1
    # A per-fill node budget so a layout that does not fill quickly is abandoned and the
    # search moves on -- which is what makes the *outer* loop (attempt after attempt) visible.
    budget = int(a[5]) if len(a) > 5 else 10_000

    print(f"=== {rows}x{cols} capped <= {max_len}, floor {floor}, seed {seed}, "
          f"fill-budget {budget:,} ===\n")

    print("--- (1) LoggingProbe: the event stream, one line each ---")
    found = fill(rows, cols, max_len, floor, seed, probe=LoggingProbe(),
                 node_budget=budget, max_patterns=40)

    print("\n--- (2) HeartbeatProbe: same search, one live line ---")
    fill(rows, cols, max_len, floor, seed, probe=HeartbeatProbe(sys.stdout.write),
         node_budget=budget, max_patterns=40)

    print("\n--- (3) the proof-vs-budget tag ---")
    print("  a complete search of a provably-empty layout space (odd black count, no centre):")
    fill(6, 6, 5, floor, seed, probe=LoggingProbe(lambda s: print("   " + s)), num_black=1)
    print("  the same shape under a node/pattern budget (a miss is not a proof):")
    fill(rows, cols, max_len, floor, seed, probe=LoggingProbe(lambda s: print("   " + s)),
         node_budget=1500, max_patterns=5)

    if found is not None:
        grid, assign = found
        fg = filled_from_blocked(grid, assign)
        print("\nresult (from run 1):")
        for row in fg.cells:
            print("  " + " ".join((x.upper() if x else "#") for x in row))


if __name__ == "__main__":
    main()
