"""Sampler strategy comparison: how should the stochastic engine reach a
*distinct* double word square? (benchmark)

  gate    -- pure min-conflicts on feasibility; restart when it lands on a valid
             but degenerate grid (a fixed point of the feasibility move).
  penalty -- fold a duplicate-pair penalty into the move so the descent is pulled
             off the degenerate basin toward a genuine square without restarting.

Backtracking (complete) is shown alongside as the reference. Usage:
    uv run scripts/samplers.py [N] [thresholds...]
"""

import sys
import time

from puzzledesk.bootstrap import build
from puzzledesk.core.engines import backtrack
from puzzledesk.core.engines.sampler import solve as sample_solve
from puzzledesk.core.square import DoubleSquare
from puzzledesk.core.validate import validate


def _run(label, run, sq, T, tries):
    solved, times, found = 0, [], set()
    for seed in range(tries):
        t0 = time.perf_counter()
        state = run(seed)
        times.append(time.perf_counter() - t0)
        if state is not None:
            assert validate(sq, state, T).ok, f"{label} emitted a non-acceptable grid"
            solved += 1
            found.add(tuple(sq.rows.words[i] for i in state))
    ms = sum(times) / len(times) * 1e3
    print(
        f"  {label:16s}: solved {solved:2d}/{tries} | {len(found):2d} distinct grids | "
        f"{ms:8.1f} ms/run"
    )


def compare(container, n, T, tries=10):
    lex = container.lexicon.load("scored", n).filtered(T)
    sq = DoubleSquare(lex)
    rf = container.rng_factory
    print(f"\n=== N={n} T={T} ({len(lex)} words), distinct=True ===")

    def sampler(guided):
        def run(seed):
            r = sample_solve(
                sq,
                rng=rf.create(seed),
                distinct=True,
                guided=guided,
                max_steps=500,
                max_restarts=200,
            )
            return r.state if r.solved else None

        return run

    _run("sampler gate", sampler(False), sq, T, tries)
    _run("sampler penalty", sampler(True), sq, T, tries)
    _run("backtrack", lambda s: backtrack.solve(sq, rng=rf.create(s), distinct=True), sq, T, tries)


if __name__ == "__main__":
    container = build()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    ts = [float(x) for x in sys.argv[2:]] if len(sys.argv) > 2 else [3.0, 3.5]
    for T in ts:
        compare(container, n, T)
