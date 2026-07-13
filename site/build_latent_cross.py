"""Build site/latent-cross.html -- Latent, the sparse two-spine CROSS.

The third companion in the scaling arc (docs/relational-difficulty.md, "Scaling Latent").
Latent · Two put two 9-spines side by side (diluted); the strict "kissing squares" crossed them
for a true central focus but was lexically infeasible (obscure-only fill). This is the loosened
middle: two *7*-letter spines (a 7-across and a 7-down) crossing at the centre cell, with
staggered 3-4 letter arms pinwheeling into two sparse clusters (~35% white). Loosening the coupling
(shorter spines, staggered arms) buys back the common vocabulary the kissing squares lost --
ESSENCE and OBSERVE cross at the centre, both real words.

The cost of the loosening: (1) the two spines share the centre letter, so one of them must be
clued to force the other (only one spine is *deduced*), and (2) sparsity flattens the cascade
(depth ~2 -- the shallowest of the variants). It is the sparse end of the space: striking to look
at, a lighter solve. Layout fixed; fill a reproducible seed search; clues authored by hand.

    uv run site/build_latent_cross.py
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
from relational import _entries, information_floor, propagate  # noqa: E402

TEMPLATE = [  # sparse pinwheel: 7-across (row4) x 7-down (col4) crossing at centre, staggered arms
    "#########", "##...####", "#....####", "#....####", "#.......#",
    "####....#", "####....#", "####...##", "#########",
]
SEED, BAR = 159, 50.0
OUT = ROOT / "site" / "latent-cross.html"

CLUES = {
    "BOO": "Ghost's greeting", "ARAB": "Peninsula native", "YAKS": "Shaggy Himalayan oxen",
    "ESSENCE": "Core nature", "REAM": "500 sheets of paper", "VETO": "Presidential no",
    "EDS": "Newspaper bosses, briefly", "AYE": "Sailor's yes", "BRAS": "Support garments",
    "OAKS": "Acorn trees", "OBSERVE": "Watch closely", "NEED": "Absolute requirement",
    "CATS": "Musical with 'Memory'", "EMO": "Angsty rock genre",
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
    clued, depth = information_floor(entries, nc)  # 14 entries -> exhaustive minimal floor
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
    sevens = [e for e in ents if e["len"] == 7]
    print("grid:", " ".join(e["answer"] for e in ents))
    print("spines:", [(e["label"], e["answer"], e["role"]) for e in sevens])
    print(f"floor {len(clued)}/{len(entries)}  depth {depth}  minvis {minvis}")
    return data


def main() -> None:
    data = build_data()
    src = (ROOT / "site" / "build_flagship.py").read_text()
    tmpl = re.search(r'_TEMPLATE = r"""(.*?)"""\n', src, re.S).group(1)
    d = data["debrief"]
    tmpl = _generalize(tmpl, data["rows"], data["cols"], d["given"], d["deduced"], d["total"])
    tmpl = tmpl.replace(
        "puzzledesk · a low-density 9×9 with a staggered 9-letter spine; the crossings force the "
        "ten unclued answers; clues authored by hand; every answer checked in your browser, never stored.",
        "puzzledesk · a sparse two-spine cross (ESSENCE × OBSERVE), ~35% white — the loosened cross: "
        "two 7-letter spines meet at the centre, the arms pinwheel out; clues authored by hand; "
        "every answer checked in your browser, never stored.",
    )
    OUT.write_text(tmpl.replace("/*DATA*/", json.dumps(data, separators=(",", ":"))), "utf-8")
    print("wrote", OUT.name)


if __name__ == "__main__":
    main()
