"""Smoke test / demo (benchmark driver).

At N=2 we enumerate every valid double word square and assert the backtracker only
ever emits real ones (energy-model ground truth). Above N=2, energy()==0 already
guarantees validity by construction, so we report solve-rate, diversity and
timing instead of enumerating.

Uses the same injected adapters as everything else: the word list via the
container's ``lexicon`` source, randomness via its ``rng_factory``. The N=2
ground-truth contract is also encoded as a proper test (tests/test_ground_truth.py).
"""

import time

from puzzledesk.bootstrap import build
from puzzledesk.core.engines import backtrack
from puzzledesk.core.engines.bruteforce import enumerate_squares
from puzzledesk.core.square import DoubleSquare


def rows_of(sq, state):
    return tuple("".join(chr(int(c) + 97) for c in sq.rows.letters[idx]) for idx in state)


def check(container, n: int, tries: int = 30, ground_truth: bool = False):
    lex = container.lexicon.load("words", n)
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
        # distinct=False so the ground-truth subset check spans EVERY valid square
        # (including the diagonally-symmetric ones brute force enumerates).
        state = backtrack.solve(sq, rng=container.rng_factory.create(seed), distinct=False)
        if state is not None:
            solved += 1
            assert sq.energy(state) == 0  # never emit an invalid square
            rows = rows_of(sq, state)
            found.add(rows)
            if truth is not None:
                assert rows in truth, f"backtrack produced {rows} not in ground truth!"
    dt = time.perf_counter() - t0

    print(
        f"backtrack: solved {solved}/{tries}  |  {len(found)} distinct  |  "
        f"{dt / tries * 1e3:.1f} ms/run"
    )
    if found:
        print("  example:\n" + "\n".join("    " + " ".join(w) for w in sorted(found)[0]))


def main():
    container = build()
    check(container, 2, ground_truth=True)
    check(container, 3)
    check(container, 4, tries=20)


if __name__ == "__main__":
    main()
