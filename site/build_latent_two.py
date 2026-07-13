"""Build site/latent-two.html -- Latent, the TWO-spine comparison grid.

A companion to the single-spine low-density variant (site/build_latent_long.py). Same low-density
9x9 idea, but with TWO 9-letter across spines (PHEASANTS and COOPERATE). It exists to make a
finding concrete (docs/relational-difficulty.md, "Scaling Latent"): a second spine competes for the
same crossers, so the deduction economy degrades sharply --

  * the clue floor jumps to ~half the grid (greedy floor 15/28 vs the single spine's 8/18) --
    each hub's crossers must be clued, so far fewer answers are free;
  * the cascade flattens (depth 3 vs 5) -- two hubs short-circuit the chain;
  * the gap between the spines is forced into eighteen 3-letter crossers (abbreviation soup).

The upside is the same one the single spine shows, doubled: both spines are over-determined by
their nine crossings, so they can be showy/obscure "for free". This page reuses the single-spine
build machinery (the flagship template generalised for black cells / non-square / parameterised
copy); the floor is *greedy* (28 entries is far past the exhaustive-floor ceiling).

    uv run site/build_latent_two.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "site"))
from build_latent_long import _cascade, _generalize, _rating  # noqa: E402
from puzzledesk.app.puzzle import filled_from_blocked  # noqa: E402
from puzzledesk.bootstrap import build  # noqa: E402
from puzzledesk.core.blocked import BlockedGrid  # noqa: E402
from puzzledesk.core.engines import fill  # noqa: E402
from relational import _entries, _greedy_floor, propagate  # noqa: E402

TEMPLATE = [  # 9x9, two 9-across spines (rows 2 and 6), staggered, 180-symmetric
    "....#####", ".....####", ".........", "####.....", "....#....",
    ".....####", ".........", "####.....", "#####....",
]
SEED, BAR = 165, 60.0
OUT = ROOT / "site" / "latent-two.html"

CLUES = {
    "RUNG": "Ladder step", "EGYPT": "Land of the Nile", "PHEASANTS": "Long-tailed game birds",
    "ADIEU": "French farewell", "APES": "Great mimics", "STEP": "Stair unit",
    "OHGOD": "Cry of dread", "COOPERATE": "Work together", "FILET": "Boneless cut",
    "BETA": "Pre-release software", "REP": "Sales agent, for short", "AOC": "Rep. Ocasio-Cortez",
    "UGH": "Grunt of disgust", "PHO": "Vietnamese noodle soup", "NYE": "Science Guy Bill",
    "EGO": "Sense of self", "GPA": "Transcript fig.", "SOP": "Gravy-soaked morsel",
    "TSA": "Airport security org.", "DEF": "Cool, in dated slang", "ADS": "Commercials",
    "RIB": "Tease good-naturedly", "NIT": "Louse egg", "ALE": "Pub pour", "TEE": "Golf peg",
    "TET": "Vietnamese New Year", "SUP": "Have dinner", "ETA": "Arrival fig.",
}


def build_data() -> dict:
    c = build()
    g = BlockedGrid.parse(TEMPLATE, min_len=3)
    assert not g.orphans, f"template not fully checked: {g.orphans}"
    maxlen = max(s.length for s in g.slots)
    full = c.lexicon.load_multi("cw", range(3, maxlen + 1))
    gen = c.lexicon.load_multi("cw", range(3, maxlen + 1), min_score=BAR)
    nc = lambda a, k: full.get(len(a)).n_candidates(a, k)  # noqa: E731
    assign = fill.solve(g, gen, rng=c.rng_factory.create(SEED), distinct=True, node_budget=200000)
    assert assign is not None, "fill failed"
    grid = filled_from_blocked(g, assign)
    entries = _entries(grid)
    clued, depth = _greedy_floor(entries, nc)  # 28 entries -> greedy (exhaustive is infeasible)
    prop = propagate(entries, set(clued), nc)
    casc = _cascade(entries, clued, nc)
    minvis = min(v for _, _, v in casc)
    ice_e, _, ice_vis = casc[0]
    last_e, last_w, _ = casc[-1]
    lengths = sorted({s.length for s in g.slots})
    vocab = sorted({w.upper() for length in lengths for w in gen.get(length).words})
    R, C = grid.rows, grid.cols

    def ej(e):
        return {
            "num": int(e.label[:-1]), "dir": e.label[-1], "label": e.label,
            "answer": e.answer.upper(), "len": len(e.cells),
            "cells": [[r, col] for (r, col) in e.cells],
            "role": "given" if e.eid in clued else "deduced",
            "clue": CLUES.get(e.answer.upper(), "(see grid)") if e.eid in clued else "",
            "wave": prop.wave_of[e.eid],
        }

    ents = [ej(e) for e in entries]
    data = {
        "rows": R, "cols": C,
        "cells": [[(grid.cells[r][col].upper() if grid.cells[r][col] else None) for col in range(C)] for r in range(R)],
        "numbering": {f"{r},{col}": n for (r, col), n in grid.numbering().items()},
        "across": [e for e in ents if e["dir"] == "A"],
        "down": [e for e in ents if e["dir"] == "D"],
        "vocab": vocab,
        "debrief": {
            "given": len(clued), "deduced": len(entries) - len(clued), "total": len(entries),
            "depth": depth, "minvis": minvis, "rating": _rating(minvis, depth),
            "ice": {"label": ice_e.label, "answer": ice_e.answer.upper(), "vis": ice_vis, "len": len(ice_e.cells)},
            "last": {"label": last_e.label, "answer": last_e.answer.upper(), "wave": last_w},
        },
        "seed": SEED,
    }
    missing = [e["answer"] for e in ents if e["role"] == "given" and e["clue"] == "(see grid)"]
    assert not missing, f"missing clues for given words: {missing}"
    print("grid:", " ".join(e["answer"] for e in ents))
    print(f"floor {len(clued)}/{len(entries)}  depth {depth}  minvis {minvis}")
    print("spines deduced:", [e["answer"] for e in ents if e["len"] == 9 and e["role"] == "deduced"])
    return data


def main() -> None:
    data = build_data()
    src = (ROOT / "site" / "build_flagship.py").read_text()
    tmpl = re.search(r'_TEMPLATE = r"""(.*?)"""\n', src, re.S).group(1)
    d = data["debrief"]
    tmpl = _generalize(tmpl, data["rows"], data["cols"], d["given"], d["deduced"], d["total"])
    # two-spine footer override
    tmpl = tmpl.replace(
        "puzzledesk · a low-density 9×9 with a staggered 9-letter spine; the crossings force the "
        "ten unclued answers; clues authored by hand; every answer checked in your browser, never stored.",
        "puzzledesk · a two-spine 9×9 (PHEASANTS and COOPERATE) — the comparison grid: a second "
        "spine competes for crossers, so the floor climbs and the cascade flattens; clues authored "
        "by hand; every answer checked in your browser, never stored.",
    )
    OUT.write_text(tmpl.replace("/*DATA*/", json.dumps(data, separators=(",", ":"))), "utf-8")
    print("wrote", OUT.name)


if __name__ == "__main__":
    main()
