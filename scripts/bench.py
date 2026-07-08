"""Performance magnitude check for a given order N (benchmark driver)."""

import sys
import time

from puzzledesk.bootstrap import build
from puzzledesk.core.engines.sampler import solve
from puzzledesk.core.square import DoubleSquare


def bench(container, n, tries=20, temperature=0.0, max_steps=2000, max_restarts=400):
    lex = container.lexicon.load("words", n)
    sq = DoubleSquare(lex)
    solved, times, steps, restarts, fail_energy = 0, [], [], [], []
    found = set()
    for seed in range(tries):
        t0 = time.perf_counter()
        r = solve(
            sq,
            rng=container.rng_factory.create(seed),
            temperature=temperature,
            max_steps=max_steps,
            max_restarts=max_restarts,
        )
        dt = time.perf_counter() - t0
        times.append(dt)
        if r.solved:
            solved += 1
            steps.append(r.steps)
            restarts.append(r.restarts)
            found.add(tuple("".join(chr(int(c) + 97) for c in sq.rows.letters[i]) for i in r.state))
        else:
            fail_energy.append(r.energy)
    avg = sum(times) / len(times)
    print(
        f"N={n} ({len(lex)} words) T={temperature}: solved {solved}/{tries} "
        f"| {len(found)} distinct | avg {avg * 1e3:.0f} ms/run"
    )
    if steps:
        print(
            f"    solved: median {sorted(steps)[len(steps) // 2]} steps, "
            f"{sorted(restarts)[len(restarts) // 2]} restarts"
        )
    if fail_energy:
        print(f"    failures: residual energy {sorted(fail_energy)}")
    if found:
        ex = sorted(found)[0]
        print("    example:\n" + "\n".join("      " + " ".join(w) for w in ex))


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    bench(build(), n)
