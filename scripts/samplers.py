"""Sampler strategy comparison: how should the stochastic engine reach a
*distinct* double word square?

Two strategies for the same distinctness constraint, same acceptance bar:

  gate    -- pure min-conflicts on feasibility; when it lands on a valid grid
             that is degenerate (a word repeats, e.g. the symmetric basin) it
             restarts. Simple, but the degenerate grid is a fixed point of the
             feasibility move, so every hit is a wasted restart.
  penalty -- fold a duplicate-pair penalty into the move (weighted below one
             valid column) so the descent is pulled off the degenerate basin
             toward a genuine square without restarting.

Backtracking (complete) is shown alongside as the reference the sampler is being
measured against. Usage: python3 scripts/samplers.py [N] [thresholds...]
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from puzzledesk import backtrack
from puzzledesk.lexicon import Lexicon
from puzzledesk.sampler import solve as sample_solve
from puzzledesk.square import DoubleSquare
from puzzledesk.validate import validate

DATA = Path(__file__).resolve().parent.parent / "data"


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
    print(f"  {label:16s}: solved {solved:2d}/{tries} | {len(found):2d} distinct grids | {ms:8.1f} ms/run")


def compare(n, T, tries=10):
    lex = Lexicon.from_scored_file(DATA / f"scored_{n}.txt", length=n).filtered(T)
    sq = DoubleSquare(lex)
    print(f"\n=== N={n} T={T} ({len(lex)} words), distinct=True ===")

    def sampler(guided):
        def run(seed):
            r = sample_solve(sq, seed=seed, distinct=True, guided=guided,
                             max_steps=500, max_restarts=200)
            return r.state if r.solved else None
        return run

    _run("sampler gate", sampler(False), sq, T, tries)
    _run("sampler penalty", sampler(True), sq, T, tries)
    _run("backtrack", lambda s: backtrack.solve(sq, seed=s, distinct=True), sq, T, tries)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    ts = [float(x) for x in sys.argv[2:]] if len(sys.argv) > 2 else [3.0, 3.5]
    for T in ts:
        compare(n, T)
