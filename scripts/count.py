"""How *large* is the solution space at a bar? (benchmark)

Every other ceiling number in this repo is time-to-*first*-grid or an UNSAT proof.
This driver asks the complementary question docs/open-questions.md flagged unbuilt:
**how many distinct minis exist at score >= X**. Because backtracking is complete,
``backtrack.count`` walks the whole tree, so near the ceiling the answer is an
*exact* finite number (a theorem) -- you watch the space go from astronomically-many
(capped at ``--limit``, reported ``>=``) to a countable handful to zero (UNSAT) as the
bar rises. ``nodes`` is the search-tree size (deterministic, container-independent).

Usage:
    count.py [N] [listname] [--limit K] [thresholds...]
      count.py 5 cw --limit 200000 90
      count.py 5 scored 3.5 3.7 3.9 4.0
"""

import sys
import time

from puzzledesk.bootstrap import build
from puzzledesk.core.engines import backtrack
from puzzledesk.core.square import DoubleSquare


def _fmt(res: backtrack.SolutionCount) -> str:
    if res.n == 0 and res.exact:
        return "UNSAT (exactly 0 -- a theorem)"
    if res.exact:
        return f"exactly {res.n} distinct minis"
    return f">= {res.n} (capped; space not exhausted)"


def sweep(container, n, thresholds, listname, limit):
    full = container.lexicon.load(listname, n)
    print(f"\n=== N={n} solution-space sweep [{listname}] (full {len(full)} words) ===")
    print(f"    (limit {limit}; 'exactly K' is an exhaustive count -- a theorem)")
    for T in thresholds:
        kept = [w for w, s in full.score_map.items() if s >= T]
        if len(kept) < n:
            print(f" T={T}: only {len(kept)} words, skipping")
            continue
        sq = DoubleSquare(full.filtered(T))
        t0 = time.perf_counter()
        res = backtrack.count(sq, limit=limit)
        ms = (time.perf_counter() - t0) * 1e3
        print(f" T={T}: {len(kept):5d} words | {_fmt(res)} | {res.nodes:>12,} nodes | {ms:8.1f} ms")


if __name__ == "__main__":
    args = sys.argv[1:]
    limit = 200_000
    if "--limit" in args:
        i = args.index("--limit")
        limit = int(args[i + 1])
        args = args[:i] + args[i + 2 :]
    n = int(args[0]) if args else 5
    listname = "scored"
    rest = args[1:]
    if rest and not rest[0].replace(".", "").isdigit():
        listname, rest = rest[0], rest[1:]
    ts = (
        [float(x) for x in rest]
        if rest
        else ([80, 90] if listname == "cw" else [3.5, 3.7, 3.9, 4.0])
    )
    sweep(build(), n, ts, listname, limit)
