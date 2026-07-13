"""Build site/latent-long.html -- Latent, the low-density / long-word variant.

A companion to the dense 5x5 flagship (site/build_flagship.py). Where that grid is a fully
packed double-square, this one is a **low-density 9x9**: a staggered layout (~55% white) built
around a single 9-letter across **spine**, ESTRANGED, that carries no clue and is *deduced*
from its crossings. It exists to probe the other end of the design space (docs/relational-
difficulty.md, "Scaling Latent"):

  * full-checking forbids genuinely sparse grids, so "low density" = larger grid + more black
    with every white cell still crossed; a lone long word would drag a word-square band, so the
    spine is **staggered** (crossers step up on one side, down the other) to stay a single 9;
  * the long word is a *keystone*, not a climax -- as a hub crossing nine downs it fills fast,
    yet the information floor still places it mid-cascade (here wave 3, pinned with 6 of 9
    letters), and the larger grid recovers the cascade depth a small hub loses.

The layout is fixed; the fill is a reproducible search (seed 87, cw>=62). Clues are authored
here (not model-written) -- this is a hand-built demonstration, not the live pipeline. The page
reuses the flagship template, generalised for black cells / non-square grids / parameterised copy.

    uv run site/build_latent_long.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from puzzledesk.app.puzzle import filled_from_blocked
from puzzledesk.bootstrap import build
from puzzledesk.core.blocked import BlockedGrid
from puzzledesk.core.engines import fill
from relational import _entries, information_floor, propagate

TEMPLATE = [  # 9x9, one 9-across spine (row 4), staggered 5-letter crossers, 180-symmetric
    "....#####", "....#####", ".....####", ".....####", ".........",
    "####.....", "####.....", "#####....", "#####....",
]
SEED, BAR = 87, 62.0
OUT = ROOT / "site" / "latent-long.html"
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

CLUES = {  # one clue per word, so whichever set the floor selects is covered
    "NUDE": "In one's birthday suit", "USES": "Puts to work", "DEBTS": "IOUs",
    "GRUEL": "Thin porridge", "ESTRANGED": "No longer on speaking terms",
    "CONDO": "Owned apartment", "KNOWN": "Widely recognized", "EMIT": "Give off, as light",
    "TENS": "Perfect scores", "NUDGE": "Gentle elbow", "USERS": "App account holders",
    "DEBUT": "First appearance", "ESTER": "Fragrant organic compound",
    "SLACK": "Workplace chat app", "NONET": "Group of nine", "GNOME": "Garden statuette",
    "EDWIN": "Astronomer Hubble", "DONTS": "Do's and ___",
}


def _cascade(entries, clued, nc):
    known: set = set()
    solved: set = set()
    order: list = []
    wave = 0
    while len(solved) < len(entries):
        wave += 1
        newly = [
            e for e in entries
            if e.eid not in solved
            and (e.eid in clued or nc(e.answer, frozenset(i for i, ch in enumerate(e.cells) if ch in known)) == 1)
        ]
        if not newly:
            return None
        for e in newly:
            if e.eid not in clued:
                order.append((e, wave, sum(1 for ch in e.cells if ch in known)))
        for e in newly:
            solved.add(e.eid)
            known.update(e.cells)
    return order


def _rating(minvis: int, depth: int) -> str:
    tier = {5: 2, 4: 3, 3: 4, 2: 6}.get(minvis, 4)
    if depth >= 6:
        tier += 1
    return _DAYS[max(0, min(5, tier - 1))]


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
    clued, depth = information_floor(entries, nc)
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
    lab = {e.eid: e.label for e in entries}
    print("grid:", " ".join(e["answer"] for e in ents))
    print("given:", ", ".join(sorted(lab[i] for i in clued)))
    print(f"floor {len(clued)}/{len(entries)}  depth {depth}  minvis {minvis}")
    print("cascade:", " -> ".join(f"{e.label}={e.answer.upper()}(w{w},vis{v})" for e, w, v in casc))
    return data


def _generalize(t: str, R: int, C: int, given: int, deduced: int, total: int) -> str:
    t = t.replace('viewBox="0 0 5 5"', f'viewBox="0 0 {C} {R}"')
    t = t.replace(
        "grid-template-columns:repeat(5,1fr);grid-template-rows:repeat(5,1fr)",
        f"grid-template-columns:repeat({C},1fr);grid-template-rows:repeat({R},1fr)",
    )
    t = t.replace(
        ".board{position:relative;width:min(380px,86vw);aspect-ratio:1}",
        f".board{{position:relative;width:min(440px,90vw);aspect-ratio:{C}/{R}}}",
    )
    t = t.replace(
        "font-family:var(--mono);font-weight:600;font-size:clamp(17px,5.4vw,27px)",
        "font-family:var(--mono);font-weight:600;font-size:clamp(13px,3.6vw,22px)",
    )
    # black cells
    t = t.replace(
        '    var cell=document.createElement("div");\n'
        '    cell.className="cell"+(givenCell[key(r,c)]?" given":"");cell.id="cell-"+r+"-"+c;',
        '    var cell=document.createElement("div");cell.id="cell-"+r+"-"+c;\n'
        '    if(P.cells[r][c]===null){cell.className="cell black";grid.appendChild(cell);continue;}\n'
        '    cell.className="cell"+(givenCell[key(r,c)]?" given":"");',
    )
    t = t.replace(".cell.given{background:#141b12}", ".cell.given{background:#141b12}\n.cell.black{background:#05080a}")
    # Clear must skip black cells; initial focus must land on a white cell
    t = t.replace(
        'var inp=inputs[key(r,c)];inp.value="";inp.classList.remove("wrong");document.getElementById("cell-"+r+"-"+c).classList.remove("lit");',
        'var inp=inputs[key(r,c)];if(inp){inp.value="";inp.classList.remove("wrong");}document.getElementById("cell-"+r+"-"+c).classList.remove("lit");',
    )
    # the win() completeness check runs every keystroke — it must skip black cells (else it
    # throws on a blocked grid and the debrief never fires)
    t = t.replace(
        'var done=true;for(var r=0;r<R;r++)for(var c=0;c<C;c++)if(inputs[key(r,c)].value!==P.cells[r][c])done=false;',
        'var done=true;for(var r=0;r<R;r++)for(var c=0;c<C;c++){var w=inputs[key(r,c)];if(w&&w.value!==P.cells[r][c])done=false;}',
    )
    t = t.replace('for(var c=0;c<C&&!f;c++)f=[r,c];', 'for(var c=0;c<C&&!f;c++)if(P.cells[r][c]!==null)f=[r,c];')
    # parameterised copy
    t = t.replace(
        'Here you get only <b>four</b> clues. The other <span class="lg">six</span> answers',
        f'Here you get only <b>{given}</b> clues. The other <span class="lg">{deduced}</span> answers',
    )
    t = t.replace("Four clues in gold. The six in cyan have none", f"{given} clues in gold. The {deduced} in cyan have none")
    t = t.replace(
        'status.textContent="Solved. Four clues carried ten answers.";',
        f'status.textContent="Solved. {given} clues carried {total} answers.";',
    )
    t = t.replace("of its 5 letters showing", 'of its "+d.ice.len+" letters showing')
    t = t.replace('d.ice.vis+"/5"', 'd.ice.vis+"/"+d.ice.len')
    t = t.replace("Solve the four gold clues; the crossings force the rest.", "Solve the gold clues; the crossings force the rest.")
    t = t.replace(
        "puzzledesk · grid computed by the engines; the four given clues written live by the model; every answer checked in your browser, never stored.",
        "puzzledesk · a low-density 9×9 with a staggered 9-letter spine; the crossings force the "
        "ten unclued answers; clues authored by hand; every answer checked in your browser, never stored.",
    )
    return t


def main() -> None:
    data = build_data()
    src = (ROOT / "site" / "build_flagship.py").read_text()
    tmpl = re.search(r'_TEMPLATE = r"""(.*?)"""\n', src, re.S).group(1)
    d = data["debrief"]
    tmpl = _generalize(tmpl, data["rows"], data["cols"], d["given"], d["deduced"], d["total"])
    OUT.write_text(tmpl.replace("/*DATA*/", json.dumps(data, separators=(",", ":"))), "utf-8")
    print("wrote", OUT.name)


if __name__ == "__main__":
    main()
