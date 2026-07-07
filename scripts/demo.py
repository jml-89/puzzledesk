"""Smoke test / demo.

At N=2 we enumerate every valid double word square and assert the sampler only
ever emits real ones (energy-model ground truth). Above N=2, energy()==0 already
guarantees validity by construction, so we report solve-rate, diversity and
timing instead of enumerating (the valid set is enormous for this weak list).
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from puzzledesk.bruteforce import enumerate_squares
from puzzledesk.lexicon import Lexicon
from puzzledesk.sampler import solve
from puzzledesk.square import DoubleSquare

DATA = Path(__file__).resolve().parent.parent / "data"


def rows_of(sq, state):
    return tuple("".join(chr(int(c) + 97) for c in sq.rows.letters[idx]) for idx in state)


def check(n: int, tries: int = 30, ground_truth: bool = False):
    lex = Lexicon.from_file(DATA / f"words_{n}.txt", length=n)
    sq = DoubleSquare(lex)
    print(f"\n=== N={n}  ({len(lex)} words) ===")

    truth = None
    if ground_truth:
        truth = set(enumerate_squares(lex))
        print(f"brute force: {len(truth)} valid double word squares")

    solved = 0
    found: set[tuple[str, ...]] = set()
    t0 = time.perf_counter()
    for seed in range(tries):
        r = solve(sq, seed=seed, max_restarts=100, max_steps=500)
        if r.solved:
            solved += 1
            assert sq.energy(r.state) == 0  # never emit an invalid square
            rows = rows_of(sq, r.state)
            found.add(rows)
            if truth is not None:
                assert rows in truth, f"sampler produced {rows} not in ground truth!"
    dt = time.perf_counter() - t0

    print(f"sampler: solved {solved}/{tries}  |  {len(found)} distinct  |  {dt/tries*1e3:.1f} ms/run")
    if found:
        print("  example:\n" + "\n".join("    " + " ".join(w) for w in sorted(found)[0]))


if __name__ == "__main__":
    check(2, ground_truth=True)
    check(3)
    check(4, tries=20)
