"""Quality experiment: does folding word-frequency into the energy produce more
readable grids, at what cost to solve speed? Run on a sub-5x5 square so we stress
the quality objective without the packing also getting hard.

Metric: mean Zipf frequency across all 2N words (N across + N induced down).
Higher = more common / readable.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from puzzledesk.lexicon import Lexicon
from puzzledesk.sampler import solve
from puzzledesk.square import DoubleSquare

DATA = Path(__file__).resolve().parent.parent / "data"


def grid_words(sq, state):
    across = [sq.rows.words[i] for i in state]
    down = sq.column_strings(state)
    return across, down


def mean_zipf(sq, state):
    across, down = grid_words(sq, state)
    vals = [sq.rows.score_map[w] for w in across] + [sq.cols.score_map[w] for w in down]
    return sum(vals) / len(vals)


def run(n, quality, tries=40, temperature=0.0):
    lex = Lexicon.from_scored_file(DATA / f"scored_{n}.txt", length=n)
    sq = DoubleSquare(lex)
    solved, zipfs, times = 0, [], []
    best = None
    for seed in range(tries):
        t0 = time.perf_counter()
        r = solve(sq, seed=seed, quality=quality, temperature=temperature,
                  max_steps=800, max_restarts=200)
        times.append(time.perf_counter() - t0)
        if r.solved:
            solved += 1
            mz = mean_zipf(sq, r.state)
            zipfs.append(mz)
            if best is None or mz > best[0]:
                best = (mz, grid_words(sq, r.state))
    avg_z = sum(zipfs) / len(zipfs) if zipfs else 0
    print(f"  quality={quality:<4}: solved {solved}/{tries} | mean-zipf {avg_z:.2f} "
          f"| {sum(times)/len(times)*1e3:.0f} ms/run")
    return best


def show(label, best):
    if not best:
        return
    mz, (across, down) = best
    print(f"    {label} (mean-zipf {mz:.2f}):")
    print("      across:", ", ".join(across))
    print("      down:  ", ", ".join(down))


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    lex = Lexicon.from_scored_file(DATA / f"scored_{n}.txt", length=n)
    print(f"=== N={n} quality sweep ({len(lex)} scored words) ===")
    b0 = run(n, quality=0.0)
    b1 = run(n, quality=1.0)
    b2 = run(n, quality=4.0)
    print()
    show("quality-blind best", b0)
    show("quality=4 best", b2)
