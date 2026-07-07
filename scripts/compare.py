"""Head-to-head: sampler vs backtracking on the filtered frontier.

Both solve the SAME problem -- a distinct double word square with every word at
or above the acceptance bar (guaranteed by filtering + distinct=True) -- so the
comparison is apples-to-apples. We report solve rate, speed, and distinct-grid
diversity. Backtracking is complete; the sampler is stochastic, so at a hard bar
the sampler may fail to solve within its budget where backtracking still would.

For the two strategies the sampler itself can use to reach a distinct grid
(gate vs penalty), see scripts/samplers.py.
"""

import sys
import time
from pathlib import Path

from puzzledesk import backtrack
from puzzledesk.lexicon import Lexicon
from puzzledesk.sampler import solve as sample_solve
from puzzledesk.square import DoubleSquare
from puzzledesk.validate import validate

DATA = Path(__file__).resolve().parent.parent / "data"


def rows_of(sq, state):
    return tuple(sq.rows.words[i] for i in state)


def compare(n, T, tries=10):
    lex = Lexicon.from_scored_file(DATA / f"scored_{n}.txt", length=n).filtered(T)
    sq = DoubleSquare(lex)
    print(f"\n=== N={n} T={T} ({len(lex)} words), distinct=True ===")

    for name, run in (
        (
            "sampler   ",
            lambda s: sample_solve(sq, seed=s, distinct=True, max_steps=500, max_restarts=200),
        ),
        ("backtrack ", lambda s: backtrack.solve(sq, seed=s, distinct=True)),
    ):
        solved, times, found = 0, [], set()
        for seed in range(tries):
            t0 = time.perf_counter()
            res = run(seed)
            times.append(time.perf_counter() - t0)
            state = res.state if hasattr(res, "state") else res
            ok = state is not None and (not hasattr(res, "solved") or res.solved)
            if ok:
                assert validate(sq, state, T).ok, f"{name} emitted a non-acceptable grid"
                solved += 1
                found.add(rows_of(sq, state))
        ms = sum(times) / len(times) * 1e3
        print(f"  {name}: solved {solved}/{tries} | {len(found)} distinct | {ms:8.1f} ms/run")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    for T in [float(x) for x in (sys.argv[2:] or [3.0, 3.5])]:
        compare(n, T)
