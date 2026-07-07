"""How high can the acceptance bar go and still pack an N x N grid?

Backtracking is complete, so at each threshold we learn one of three things:
solutions exist (and how fast we find distinct ones), or no grid exists at all
(true UNSAT), or the list is too small to matter. Sweep T upward to find the
quality ceiling.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from puzzledesk import backtrack
from puzzledesk.lexicon import Lexicon
from puzzledesk.square import DoubleSquare
from puzzledesk.validate import validate

DATA = Path(__file__).resolve().parent.parent / "data"


def sweep(n, thresholds, tries=25):
    full = Lexicon.from_scored_file(DATA / f"scored_{n}.txt", length=n)
    print(f"\n=== N={n} ceiling sweep (full {len(full)} words) ===")
    for T in thresholds:
        lex = full.filtered(T)
        if len(lex) < n:
            print(f" T={T}: only {len(lex)} words, skipping")
            continue
        sq = DoubleSquare(lex)
        solved, times, found, best = 0, [], set(), None
        for seed in range(tries):
            t0 = time.perf_counter()
            state = backtrack.solve(sq, seed=seed)
            times.append(time.perf_counter() - t0)
            if state is not None:
                solved += 1
                found.add(tuple(sq.rows.words[i] for i in state))
                v = validate(sq, state, T)
                if best is None or v.min_score > best[0]:
                    best = (v.min_score, [sq.rows.words[i] for i in state])
        ms = sum(times) / len(times) * 1e3
        verdict = "UNSAT" if solved == 0 else f"{len(found)} distinct"
        print(f" T={T}: {len(lex):4d} words | solved {solved}/{tries} ({verdict}) | {ms:6.1f} ms")
        if best:
            print(f"        best-min grid ({best[0]:.1f}): {' / '.join(best[1])}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    ts = [float(x) for x in sys.argv[2:]] if len(sys.argv) > 2 else [4.0, 4.5, 5.0, 5.5, 6.0]
    sweep(n, ts)
