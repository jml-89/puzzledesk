"""Map the feasibility/quality frontier -- the stochastic view.

For each acceptance threshold T, filter the lexicon to words >= T, solve for a
distinct double word square with the sampler, and validate. Because we filtered
at T, every solved grid passes the min-word acceptance test by construction -- so
the only questions are: does it still pack (into a genuine, distinct square), and
how fast?

The highest T that still packs reliably is the best 'all words acceptable' bar
we can hold for that order N. This is the sampler's picture; ceiling.py draws the
same frontier with the *complete* solver, which additionally proves UNSAT above
the ceiling (the sampler can only fail to find one, never prove none exists).
"""

import sys
import time
from pathlib import Path

from puzzledesk.lexicon import Lexicon
from puzzledesk.sampler import solve
from puzzledesk.square import DoubleSquare
from puzzledesk.validate import validate

DATA = Path(__file__).resolve().parent.parent / "data"


def frontier(n, thresholds, tries=20):
    full = Lexicon.from_scored_file(DATA / f"scored_{n}.txt", length=n)
    print(f"\n=== N={n}  (full scored list: {len(full)} words) ===")
    print(f"{'T':>4} {'words':>6} {'solved':>8} {'ms/run':>7}  example (weakest word)")
    for T in thresholds:
        lex = full.filtered(T)
        if len(lex) < n:
            print(f"{T:>4} {len(lex):>6}   too few words")
            continue
        sq = DoubleSquare(lex)
        solved, times, best = 0, [], None
        for seed in range(tries):
            t0 = time.perf_counter()
            r = solve(sq, seed=seed, distinct=True, max_steps=500, max_restarts=200)
            times.append(time.perf_counter() - t0)
            if r.solved:
                solved += 1
                v = validate(sq, r.state, T)
                assert v.ok, f"filtered solve violated the bar: {v}"  # sanity
                if best is None or v.min_score > best.min_score:
                    best = v
        ms = sum(times) / len(times) * 1e3
        ex = ""
        if best:
            across = ", ".join(w for w, _ in best.words[:n])
            ex = f"{across}  (weakest {best.weakest[0]!r}={best.weakest[1]:.1f})"
        print(f"{T:>4} {len(lex):>6} {solved:>3}/{tries:<4} {ms:>7.0f}  {ex}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    tries = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    ts = [float(x) for x in sys.argv[3:]] if len(sys.argv) > 3 else [2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    frontier(n, ts, tries=tries)
