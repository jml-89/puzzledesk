"""Structural + solve-order difficulty of generated minis (benchmark).

Solves distinct minis at a score band, projects each to the canonical FilledGrid, and
reports two readings of difficulty against the *full* solving vocabulary (not the
generation-filtered list -- a solver knows every word, D21/D22):

  * STATIC (``app.difficulty.analyze``): each crossing is *open* if neither crossing
    word alone pins the shared letter -- a Natick *risk* at maximal support. Flagged
    *unfair* only when both entries are also obscure (score < ``obscure_below``).
  * DYNAMIC (``app.difficulty.solve_order``): replay the fill easiest-first -- forced
    entries (unique fit), then gimmes (score >= ``gimme``, known from the clue), else a
    *hard* get (stuck: obscure and still open). The bottleneck hard-get is what makes a
    grid a Saturday; an obscure word that its crossings *force* by the time you reach it
    is not a Natick -- which the static reading cannot tell.

    uv run scripts/difficulty.py [N] [listname] [min] [max] [obscure_below] [--gimme G]
    uv run scripts/difficulty.py blocked ROWS COLS NUM_BLACK [min] [obscure_below] [--gimme G]

Numbers go to docs/notes.md.
"""

import sys

from puzzledesk.app.difficulty import analyze, solve_order
from puzzledesk.app.puzzle import filled_from_blocked, filled_from_square
from puzzledesk.bootstrap import build
from puzzledesk.core.engines import backtrack, patterns
from puzzledesk.core.lexicon import encode
from puzzledesk.core.square import DoubleSquare

_OBSCURE = {"cw": 60.0, "scored": 3.0}  # per-list "below this is obscure" (cw: below "solid")
_GIMME = {"cw": 80.0, "scored": 4.0}  # per-list "known from the clue" cutoff (D21 layer B)
_SYM = {"forced": "F", "gimme": "G", "hard": "H"}


def _render(grid):
    return "\n".join(
        " ".join(
            "#" if grid.cells[r][c] is None else grid.cells[r][c].upper() for c in range(grid.cols)
        )
        for r in range(grid.rows)
    )


def _pattern(word, known):
    return [c if i in known else None for i, c in enumerate(encode(word))]


def _emit(grid, options, candidates, score_of, obscure_below, gimme):
    """Analyze one FilledGrid (static + dynamic), print it, return per-grid stats."""
    diff = analyze(grid, options)
    answer = {t.id: t.answer for t in grid.runs()}
    across = [t.answer for t in grid.runs() if t.kind == "A"]
    down = [t.answer for t in grid.runs() if t.kind == "D"]
    opens = diff.open_crossings
    # A Natick is an open crossing where *both* entries are obscure.
    unfair = [
        c
        for c in opens
        if max(score_of(answer[c.across]), score_of(answer[c.down])) < obscure_below
    ]
    rate = 100.0 * len(opens) / len(diff.crossings) if diff.crossings else 0.0
    print(f"\n{_render(grid)}")
    print(f"  across: {', '.join(across)}  |  down: {', '.join(down)}")
    print(
        f"  static: crossings {len(diff.crossings)}  open {len(opens)} ({rate:.0f}%)  "
        f"unfair {len(unfair)}  max ambiguity {diff.max_ambiguity}"
    )

    traj = solve_order(grid, candidates, score_of, gimme=gimme)
    b = traj.bottleneck
    btxt = (
        f"  bottleneck {b.answer}({b.score:.0f}) among {b.candidates} @step{b.order}" if b else ""
    )
    ng, nf, nh = (len(traj.of_kind(k)) for k in ("gimme", "forced", "hard"))
    print(f"  dynamic: {''.join(_SYM[s.kind] for s in traj.steps)}  {ng}g {nf}f {nh}h{btxt}")
    for s in traj.hard_gets:
        print(f"    hard @step{s.order}: {s.answer}({s.score:.0f}) among {s.candidates} fits")

    return {
        "open": len(opens),
        "unfair": len(unfair),
        "hard": len(traj.hard_gets),
        "bylen": [
            (min(len(answer[c.across]), len(answer[c.down])), c.is_open) for c in diff.crossings
        ],
    }


def _summary(stats, *, bylen=False):
    if not stats:
        print("\nno grid at this band (UNSAT or list too small)")
        return
    g = len(stats)

    def avg(key):
        return sum(s[key] for s in stats) / g

    print(
        f"\nsummary: {g} grids | open/grid avg {avg('open'):.1f} | "
        f"unfair/grid avg {avg('unfair'):.1f} | hard-gets/grid avg {avg('hard'):.1f} "
        f"(max {max(s['hard'] for s in stats)})"
    )
    if bylen:
        rows = [row for s in stats for row in s["bylen"]]
        print("open rate by shorter-entry length (the weak side of each crossing):")
        for length in sorted({ln for ln, _ in rows}):
            flags = [is_open for ln, is_open in rows if ln == length]
            opened, total = sum(flags), len(flags)
            print(f"  len {length}: {opened:3d}/{total:3d} open ({100 * opened / total:.0f}%)")


def report_square(
    container, n, listname, min_score, max_score, obscure_below, gimme, count=5, tries=300
):
    full = container.lexicon.load(listname, n)  # the whole vocabulary a solver has
    band = f">= {min_score:g}" if max_score is None else f"in [{min_score:g}, {max_score:g}]"
    print(f"\n=== {n}x{n} fully-checked [{listname}], score {band}, gimme {gimme:g} ===")
    print(
        f"generation list: {len(full.filtered(min_score, max_score))} words; "
        f"solving vocabulary: {len(full)} words; obscure < {obscure_below:g}"
    )
    sq = DoubleSquare(full.filtered(min_score, max_score))
    stats, solved = [], 0
    for seed in range(tries):
        if solved >= count:
            break
        state = backtrack.solve(sq, rng=container.rng_factory.create(seed), distinct=True)
        if state is None:
            continue
        solved += 1
        stats.append(
            _emit(
                filled_from_square(sq, state),
                full.n_letters_at,
                lambda w, kn: int(full.matching(_pattern(w, kn)).size),
                lambda w: full.score_map.get(w, 0.0),
                obscure_below,
                gimme,
            )
        )
    _summary(stats)


def report_blocked(
    container, rows, cols, num_black, min_score, obscure_below, gimme, count=5, tries=400, min_len=3
):
    lengths = range(min_len, max(rows, cols) + 1)
    full = container.lexicon.load_multi("cw", lengths)  # full vocab, all lengths
    gen = container.lexicon.load_multi("cw", lengths, min_score=min_score)
    print(
        f"\n=== {rows}x{cols} blocked [cw], {num_black} black, "
        f"score >= {min_score:g}, gimme {gimme:g} ==="
    )
    print(
        f"solving vocabulary by length: "
        f"{ {n: len(full.get(n)) for n in lengths} }; obscure < {obscure_below:g}"
    )

    def options(word, pos):
        return full.get(len(word)).n_letters_at(word, pos)

    def candidates(word, known):
        return int(full.get(len(word)).matching(_pattern(word, known)).size)

    def score_of(word):
        return full.get(len(word)).score_map.get(word, 0.0)

    stats, solved = [], 0
    for seed in range(tries):
        if solved >= count:
            break
        found = patterns.fill_by_count(
            rows, cols, num_black, gen, rng_factory=container.rng_factory, seed=seed, distinct=True
        )
        if found is None:
            continue
        grid, assign = found
        solved += 1
        stats.append(
            _emit(
                filled_from_blocked(grid, assign),
                options,
                candidates,
                score_of,
                obscure_below,
                gimme,
            )
        )
    _summary(stats, bylen=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    gimme_override = None
    if "--gimme" in args:
        i = args.index("--gimme")
        gimme_override = float(args[i + 1])
        args = args[:i] + args[i + 2 :]
    if args and args[0] == "blocked":
        rows = int(args[1]) if len(args) > 1 else 5
        cols = int(args[2]) if len(args) > 2 else 5
        num_black = int(args[3]) if len(args) > 3 else 4
        min_score = float(args[4]) if len(args) > 4 else 60.0
        obscure_below = float(args[5]) if len(args) > 5 else _OBSCURE["cw"]
        gimme = gimme_override if gimme_override is not None else _GIMME["cw"]
        report_blocked(build(), rows, cols, num_black, min_score, obscure_below, gimme)
    else:
        n = int(args[0]) if args else 5
        listname = args[1] if len(args) > 1 else "cw"
        min_score = float(args[2]) if len(args) > 2 else 90.0
        max_score = float(args[3]) if len(args) > 3 else None
        obscure_below = float(args[4]) if len(args) > 4 else _OBSCURE.get(listname, 60.0)
        gimme = gimme_override if gimme_override is not None else _GIMME.get(listname, 80.0)
        report_square(build(), n, listname, min_score, max_score, obscure_below, gimme)
