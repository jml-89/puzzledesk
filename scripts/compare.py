"""Head-to-head: sampler vs backtracking on the filtered frontier.

Both must clear the same acceptance bar (guaranteed by filtering). We compare
solve rate, speed, and distinct-grid diversity.
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


def rows_of(sq, state):
    return tuple(sq.rows.words[i] for i in state)


def compare(n, T, tries=20):
    lex = Lexicon.from_scored_file(DATA / f"scored_{n}.txt", length=n).filtered(T)
    sq = DoubleSquare(lex)
    print(f"\n=== N={n} T={T} ({len(lex)} words) ===")

    for name, run in (
        ("sampler   ", lambda s: sample_solve(sq, seed=s, max_steps=800, max_restarts=400)),
        ("backtrack ", lambda s: backtrack.solve(sq, seed=s)),
    ):
        solved, times, found = 0, [], set()
        for seed in range(tries):
            t0 = time.perf_counter()
            res = run(seed)
            times.append(time.perf_counter() - t0)
            state = res.state if hasattr(res, "state") else res
            ok = state is not None and (not hasattr(res, "solved") or res.solved)
            if ok and sq.energy(state) == 0:
                solved += 1
                assert validate(sq, state, T).ok
                found.add(rows_of(sq, state))
        ms = sum(times) / len(times) * 1e3
        print(f"  {name}: solved {solved}/{tries} | {len(found)} distinct | {ms:8.1f} ms/run")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    for T in [float(x) for x in (sys.argv[2:] or [3.0, 3.5, 4.0])]:
        compare(n, T)
