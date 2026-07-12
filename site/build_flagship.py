"""Build site/latent.html -- the flagship endogenous puzzle: the latent logic puzzle.

Every crossword is two puzzles superimposed: a *trivia* puzzle (clues -> answers) and a
*logic* puzzle (the crossings force answers with no clue at all). Ordinary minis play only
the first and leave the second latent. This page makes the second one the whole point:

  * you are given only the information floor -- the minimum clues (here 4 of 10);
  * the other six are recovered by pure deduction, in the exact forced order the crossing
    graph dictates -- drawn as a **thread** propagating through the grid as you solve;
  * on completion a **debrief** surfaces the invisible structure you just conquered: the
    floor, the cascade depth, and the ice-breaker -- the first entry you cracked, and how
    many words its pattern collapsed from.

The mechanic is the relational model (docs/relational-difficulty.md); this is its most
dramatic presentation. Grid chosen by a reproducible search for a deep cascade of common
words; the floor clues are written live by the model. Self-contained, no external assets.

    uv run --extra clue python site/build_flagship.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from puzzledesk.app.clue import ClueStyle, Difficulty
from puzzledesk.app.puzzle import filled_from_square
from puzzledesk.bootstrap import build
from puzzledesk.core.engines import backtrack
from puzzledesk.core.square import DoubleSquare
from relational import _entries, information_floor, propagate

FILL_BAR = 90.0
VOCAB_BAR = 50.0
COMMON_ZIPF = 3.2
MIN_DEPTH = 5  # a long, dramatic cascade
MAX_FLOOR = 4  # the strong hook: "4 clues, 6 deduced"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT = Path(__file__).resolve().parent / "latent.html"
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _oracles():
    dictw = {w.strip().lower() for w in (DATA_DIR / "words_5.txt").read_text().splitlines()}
    scored = {}
    for line in (DATA_DIR / "scored_5.txt").read_text().splitlines():
        p = line.split()
        if len(p) == 2:
            scored[p[0]] = float(p[1])
    return dictw, scored


def _cascade(entries, clued, nc):
    """Replay the forced solve. Returns, per clueless entry in solve order, (entry, wave,
    vis_at_force) -- vis_at_force is how many of its letters were showing when it became the
    unique fit (fewer = a harder deduction)."""
    known: set = set()
    solved: set = set()
    order: list = []
    wave = 0
    while len(solved) < len(entries):
        wave += 1
        newly = [
            e
            for e in entries
            if e.eid not in solved
            and (e.eid in clued or nc(e.answer, frozenset(i for i, c in enumerate(e.cells) if c in known)) == 1)
        ]
        if not newly:
            return None
        for e in newly:
            if e.eid not in clued:
                order.append((e, wave, sum(1 for c in e.cells if c in known)))
        for e in newly:
            solved.add(e.eid)
            known.update(e.cells)
    return order


def _select(c, full, nc, dictw, scored):
    common = lambda w: w in dictw and scored.get(w, 0) >= COMMON_ZIPF  # noqa: E731
    sq = DoubleSquare(full.filtered(FILL_BAR))
    for seed in range(30000):
        state = backtrack.solve(sq, rng=c.rng_factory.create(seed), distinct=True)
        if state is None:
            continue
        entries = _entries(filled_from_square(sq, state))
        floor = information_floor(entries, nc)
        if floor is None:
            continue
        clued, depth = floor
        if depth < MIN_DEPTH or len(clued) > MAX_FLOOR:
            continue
        clueless = [e for e in entries if e.eid not in clued]
        if not all(common(e.answer) for e in clueless):
            continue
        casc = _cascade(entries, clued, nc)
        if casc is None:
            continue
        return seed, filled_from_square(sq, state), entries, clued, depth, casc
    raise SystemExit("no flagship grid matched")


def _rating(minvis: int, depth: int) -> str:
    """Estimated deduction difficulty: the hardest forcing (minvis) sets the base, a long
    chain nudges it up. A heuristic, labelled as such -- the real calibration wants human logs."""
    tier = {5: 1, 4: 2, 3: 4, 2: 6}.get(minvis, 4)
    if depth >= 6:
        tier += 1
    return _DAYS[max(0, min(5, tier - 1))]


def build_data() -> dict:
    c = build()
    full = c.lexicon.load("cw", 5)
    vocab = full.filtered(VOCAB_BAR)
    nc = lambda a, k: vocab.n_candidates(a, k)  # noqa: E731
    dictw, scored = _oracles()

    seed, grid, entries, clued, depth, casc = _select(c, full, nc, dictw, scored)
    prop = propagate(entries, set(clued), nc)
    minvis = min(vis for (_, _, vis) in casc)
    ice_e, ice_w, ice_vis = casc[0]  # first clueless entry cracked (the ice-breaker)
    last_e, last_w, _ = casc[-1]  # the deepest deduction (the last domino)

    targets = [t for t in grid.runs() if t.id in clued]
    res = c.clue.clue(grid, style=ClueStyle(difficulty=Difficulty.MONDAY), targets=targets)
    clue_text = {tid: (cl.text if (cl := res.clues.get(tid)) else "") for tid in clued}

    def entry_json(e):
        return {
            "num": int(e.label[:-1]),
            "dir": e.label[-1],
            "label": e.label,
            "answer": e.answer.upper(),
            "len": len(e.cells),
            "cells": [[r, col] for (r, col) in e.cells],
            "role": "given" if e.eid in clued else "deduced",
            "clue": clue_text.get(e.eid, ""),
            "wave": prop.wave_of[e.eid],
        }

    ents = [entry_json(e) for e in entries]
    # the thread: clueless-entry centres, in forced-solve order
    thread = [
        {
            "label": e.label,
            "cx": sum(col for (_, col) in e.cells) / len(e.cells) + 0.5,
            "cy": sum(r for (r, _) in e.cells) / len(e.cells) + 0.5,
        }
        for (e, _, _) in casc
    ]
    return {
        "rows": 5,
        "cols": 5,
        "cells": [[grid.cells[r][col].upper() for col in range(5)] for r in range(5)],
        "numbering": {f"{r},{col}": n for (r, col), n in grid.numbering().items()},
        "across": [e for e in ents if e["dir"] == "A"],
        "down": [e for e in ents if e["dir"] == "D"],
        "thread": thread,
        "vocab": sorted(w.upper() for w in vocab.words),
        "debrief": {
            "given": len(clued),
            "deduced": len(entries) - len(clued),
            "depth": depth,
            "minvis": minvis,
            "rating": _rating(minvis, depth),
            "ice": {"label": ice_e.label, "answer": ice_e.answer.upper(), "vis": ice_vis},
            "last": {"label": last_e.label, "answer": last_e.answer.upper(), "wave": last_w},
        },
        "seed": seed,
    }


def main() -> None:
    data = build_data()
    OUT.write_text(_TEMPLATE.replace("/*DATA*/", json.dumps(data, separators=(",", ":"))), "utf-8")
    d = data["debrief"]
    given = [e["label"] for e in data["across"] + data["down"] if e["role"] == "given"]
    print(f"wrote {OUT.name}  seed {data['seed']}  {d['given']} given / {d['deduced']} deduced")
    print(f"  grid: {' '.join(e['answer'] for e in data['across'] + data['down'])}")
    print(f"  given clues: {given}")
    print(f"  depth {d['depth']}  minvis {d['minvis']}  rating {d['rating']}  "
          f"ice-breaker {d['ice']['label']}={d['ice']['answer']} ({d['ice']['vis']} letters)  "
          f"last domino {d['last']['label']}={d['last']['answer']} (wave {d['last']['wave']})")
    for e in data["across"] + data["down"]:
        if e["role"] == "given":
            print(f"    {e['label']} {e['answer']}  {e['clue']}")


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Latent — puzzledesk</title>
<style>
:root{
  --bg:#0b0f14;--panel:#111820;--cell:#0f151c;--edge:#243240;--edge-hi:#3a4c5e;
  --ink:#e7edf3;--muted:#8ba0b4;--faint:#54677a;--given:#f0d69b;--logic:#5fd0d6;
  --logic-dim:rgba(95,208,214,.22);--logic-soft:rgba(95,208,214,.10);--good:#7ee0a8;
  --wrong:#e8846f;--sel:rgba(95,208,214,.16);--sel-line:#5fd0d6;
  --serif:"Iowan Old Style",Georgia,"Times New Roman",serif;
  --mono:ui-monospace,"SF Mono","Cascadia Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Helvetica,sans-serif;
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(120% 90% at 50% -10%,#12202b 0%,var(--bg) 60%);
  color:var(--ink);font-family:var(--serif);line-height:1.5;-webkit-font-smoothing:antialiased;min-height:100vh}
.wrap{max-width:1020px;margin:0 auto;padding:34px 24px 80px}
a{color:var(--logic)}
.top{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:10px;
  font-family:var(--sans);font-size:11px;letter-spacing:.24em;text-transform:uppercase;color:var(--faint)}
.top a{color:var(--faint);text-decoration:none}.top a:hover{color:var(--logic)}
h1{font-family:var(--serif);font-weight:700;font-size:clamp(40px,8vw,72px);line-height:.95;
  letter-spacing:-.03em;margin:14px 0 6px}
.sub{font-size:16px;color:var(--muted);max-width:60ch;font-style:italic;margin:0}
.sub b{color:var(--given);font-style:normal;font-weight:600}
.sub .lg{color:var(--logic);font-style:normal;font-weight:600}
.rule{height:1px;background:linear-gradient(90deg,transparent,var(--edge),transparent);margin:26px 0 30px}
.play{display:grid;grid-template-columns:auto 1fr;gap:44px;align-items:start}
@media (max-width:760px){.play{grid-template-columns:1fr;gap:26px}}
.board{position:relative;width:min(380px,86vw);aspect-ratio:1}
.grid{position:absolute;inset:0;z-index:1;display:grid;grid-template-columns:repeat(5,1fr);grid-template-rows:repeat(5,1fr);
  gap:2px;background:var(--edge);border:2px solid var(--edge-hi);border-radius:4px;overflow:hidden}
.cell{position:relative;background:var(--cell);min-width:0;min-height:0}
.cell .num{position:absolute;top:2px;left:3px;font-family:var(--mono);font-size:9.5px;color:var(--faint);pointer-events:none}
.cell.given{background:#141b12}
.cell input{width:100%;height:100%;border:0;background:transparent;text-align:center;caret-color:transparent;
  font-family:var(--mono);font-weight:600;font-size:clamp(17px,5.4vw,27px);color:var(--ink);text-transform:uppercase;padding:0}
.cell.given input{color:var(--given)}
.cell input:focus{outline:none}
.cell.inline{background:var(--sel)}
.cell.active{box-shadow:inset 0 0 0 2px var(--sel-line)}
.cell input.wrong{color:var(--wrong);text-decoration:line-through}
.cell.lit input{color:var(--logic)}
.cell.pop{animation:pop .55s ease}
@keyframes pop{0%{background:var(--logic-soft)}45%{background:var(--logic);box-shadow:inset 0 0 0 2px var(--logic)}100%{}}
.thread{position:absolute;inset:0;z-index:3;width:100%;height:100%;pointer-events:none;overflow:visible}
.thread .latent{fill:none;stroke:var(--logic-dim);stroke-width:.055;stroke-dasharray:.14 .12;stroke-linecap:round;stroke-linejoin:round}
.thread .live{fill:none;stroke:var(--logic);stroke-width:.08;stroke-linecap:round;stroke-linejoin:round;
  filter:drop-shadow(0 0 4px var(--logic))}
.thread .node{fill:var(--logic);filter:drop-shadow(0 0 3px var(--logic))}
.side{display:flex;flex-direction:column;gap:20px;min-width:0}
.curline{font-family:var(--sans);font-size:14px;color:var(--ink);background:var(--panel);
  border:1px solid var(--edge);border-left:3px solid var(--given);border-radius:4px;padding:10px 13px;min-height:22px}
.curline.deduced{border-left-color:var(--logic)}
.curline b{font-family:var(--mono);margin-right:8px}
.curline.given b{color:var(--given)}.curline.deduced b{color:var(--logic)}
.curline .one{color:var(--logic);font-weight:700}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:8px 26px}
.colhead{font-family:var(--sans);font-size:11px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--faint);margin:0 0 8px;padding-bottom:6px;border-bottom:1px solid var(--edge)}
.clist{list-style:none;margin:0 0 6px;padding:0;display:flex;flex-direction:column;gap:3px}
.clist li{display:grid;grid-template-columns:24px 1fr;gap:8px;font-size:13.5px;padding:4px 6px;border-radius:4px;cursor:pointer;align-items:baseline}
.clist li:hover{background:var(--logic-soft)}
.clist li.on{background:var(--sel)}
.clist .cn{font-family:var(--mono);font-size:11px;color:var(--faint);text-align:right}
.clist li.given .ct{color:var(--muted)}
.clist li.done .ct{color:var(--faint)}
.clist li.deduced .ct{color:var(--logic)}
.clist li.deduced .ct .hint{font-family:var(--mono);font-size:11.5px;color:var(--faint)}
.clist li.deduced .ct .one{color:var(--logic);font-weight:700}
.controls{display:flex;gap:8px;flex-wrap:wrap;margin-top:2px}
.btn{font-family:var(--sans);font-size:12px;letter-spacing:.04em;padding:8px 14px;border-radius:4px;cursor:pointer;
  border:1px solid var(--edge);background:var(--panel);color:var(--ink)}
.btn:hover{border-color:var(--logic);color:var(--logic)}
.status{font-family:var(--sans);font-size:12.5px;color:var(--muted);min-height:16px}
/* debrief */
.debrief{margin-top:30px;border:1px solid var(--edge);border-radius:8px;background:linear-gradient(180deg,#101a22,#0c1319);
  padding:0;overflow:hidden;max-height:0;opacity:0;transition:max-height .6s ease,opacity .6s ease}
.debrief.show{max-height:640px;opacity:1}
.debrief .dh{font-family:var(--sans);font-size:11px;letter-spacing:.24em;text-transform:uppercase;color:var(--logic);
  padding:16px 22px 0}
.debrief h2{font-family:var(--serif);font-size:26px;margin:4px 22px 2px;letter-spacing:-.01em}
.debrief p{margin:6px 22px 14px;color:var(--muted);font-size:14.5px;max-width:70ch}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:1px;background:var(--edge);
  border-top:1px solid var(--edge);border-bottom:1px solid var(--edge)}
.stat{background:#0e161d;padding:16px 18px}
.stat .k{font-family:var(--sans);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint)}
.stat .v{font-family:var(--serif);font-size:30px;font-weight:700;color:var(--ink);line-height:1.1;margin-top:4px}
.stat .v small{font-size:15px;color:var(--muted);font-weight:400}
.stat.hl .v{color:var(--logic)}
.foot{font-family:var(--sans);font-size:12px;color:var(--faint);line-height:1.6;margin:38px 0 0;
  border-top:1px solid var(--edge);padding-top:16px}
.foot a{color:var(--faint)}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <span>puzzledesk · the latent logic puzzle</span>
    <span><a href="index.html">← all samples</a></span>
  </div>
  <h1>Latent</h1>
  <p class="sub">Every crossword is two puzzles at once: a <b>trivia</b> puzzle and a <span class="lg">logic</span> puzzle the crossings hide. Here you get only <b>four</b> clues. The other <span class="lg">six</span> answers are never given — you deduce each from the letters its crossings force. Watch the thread.</p>
  <div class="rule"></div>

  <div class="play">
    <div class="board">
      <svg class="thread" id="thread" viewBox="0 0 5 5" preserveAspectRatio="none">
        <polyline class="latent" id="latent" points=""></polyline>
        <polyline class="live" id="live" points=""></polyline>
        <g id="nodes"></g>
      </svg>
      <div class="grid" id="grid" role="group" aria-label="Crossword grid"></div>
    </div>
    <div class="side">
      <div class="curline" id="curline"></div>
      <div class="cols">
        <div><div class="colhead">Across</div><ol class="clist" id="acr"></ol></div>
        <div><div class="colhead">Down</div><ol class="clist" id="dwn"></ol></div>
      </div>
      <div class="controls"><button class="btn" id="clearBtn" type="button">Clear</button></div>
      <div class="status" id="status">Four clues in gold. The six in cyan have none — solve the gold, and the crossings force the rest, one at a time, along the thread.</div>
    </div>
  </div>

  <section class="debrief" id="debrief">
    <div class="dh">Solve debrief</div>
    <h2>You solved the puzzle no clue could.</h2>
    <p id="debriefP"></p>
    <div class="stats" id="stats"></div>
    <p style="margin-top:14px">Two puzzles were superimposed here; you played the one crosswords usually leave hidden. The full write-up: <code>docs/relational-difficulty.md</code>. More: <a href="endogenous.html">Half the Clues</a> · <a href="keystone.html">The Keystone</a>.</p>
  </section>

  <p class="foot">puzzledesk · grid computed by the engines; the four given clues written live by the model; every answer checked in your browser, never stored. <a href="index.html">back to the gallery</a>.</p>
</div>
<script>var DATA=/*DATA*/;</script>
<script>
(function(){
  var P=DATA,R=P.rows,C=P.cols,VOCAB=P.vocab;
  var all=P.across.concat(P.down),byRef={},mapA={},mapD={},numAt={};
  function key(r,c){return r+","+c;}
  P.across.forEach(function(e){byRef["A"+e.num]=e;e.cells.forEach(function(x){mapA[key(x[0],x[1])]=e;});});
  P.down.forEach(function(e){byRef["D"+e.num]=e;e.cells.forEach(function(x){mapD[key(x[0],x[1])]=e;});});
  for(var k in P.numbering)numAt[k]=P.numbering[k];
  var givenCell={};
  all.forEach(function(e){if(e.role==="given")e.cells.forEach(function(x){givenCell[key(x[0],x[1])]=true;});});

  var grid=document.getElementById("grid"),inputs={},active=null,dir="A";
  for(var r=0;r<R;r++)for(var c=0;c<C;c++){
    var cell=document.createElement("div");
    cell.className="cell"+(givenCell[key(r,c)]?" given":"");cell.id="cell-"+r+"-"+c;
    var n=numAt[key(r,c)];
    if(n){var s=document.createElement("span");s.className="num";s.textContent=n;cell.appendChild(s);}
    var inp=document.createElement("input");inp.maxLength=1;inp.autocapitalize="characters";inp.inputMode="text";
    (function(r,c,inp){
      inp.addEventListener("focus",function(){setActive(r,c,false);});
      inp.addEventListener("mousedown",function(){if(active&&active.r===r&&active.c===c)dir=(dir==="A"?"D":"A");});
      inp.addEventListener("input",function(){inp.value=(inp.value||"").toUpperCase().replace(/[^A-Z]/g,"");inp.classList.remove("wrong");if(inp.value)step(1);refresh();});
      inp.addEventListener("keydown",function(e){var k=e.key;
        if(k==="Backspace"){if(!inp.value){step(-1);var p=inputs[key(active.r,active.c)];if(p){p.value="";p.classList.remove("wrong");}e.preventDefault();refresh();}else{inp.classList.remove("wrong");}}
        else if(k==="ArrowRight"){dir="A";nudge(0,1);e.preventDefault();}else if(k==="ArrowLeft"){dir="A";nudge(0,-1);e.preventDefault();}
        else if(k==="ArrowDown"){dir="D";nudge(1,0);e.preventDefault();}else if(k==="ArrowUp"){dir="D";nudge(-1,0);e.preventDefault();}
        else if(k===" "){dir=(dir==="A"?"D":"A");render();e.preventDefault();}});
    })(r,c,inp);
    cell.appendChild(inp);grid.appendChild(cell);inputs[key(r,c)]=inp;
  }

  function cur(){var e=(dir==="A"?mapA:mapD)[key(active.r,active.c)];return e||(dir==="A"?mapD:mapA)[key(active.r,active.c)];}
  function setActive(r,c,focus){active={r:r,c:c};if(focus!==false){var el=inputs[key(r,c)];if(el)el.focus();}render();}
  function nudge(dr,dc){var nr=active.r+dr,nc=active.c+dc;if(nr>=0&&nc>=0&&nr<R&&nc<C)setActive(nr,nc,true);}
  function step(s){var e=cur();if(!e)return;for(var i=0;i<e.cells.length;i++)if(e.cells[i][0]===active.r&&e.cells[i][1]===active.c){var j=i+s;if(j>=0&&j<e.cells.length)setActive(e.cells[j][0],e.cells[j][1],true);return;}}
  function jump(e){var t=e.cells.find(function(x){return !inputs[key(x[0],x[1])].value;})||e.cells[0];dir=e.dir;setActive(t[0],t[1],true);}

  function pat(e){return e.cells.map(function(x){return inputs[key(x[0],x[1])].value||"";});}
  function fits(e){var p=pat(e);return VOCAB.filter(function(w){if(w.length!==e.len)return false;for(var i=0;i<p.length;i++)if(p[i]&&w[i]!==p[i])return false;return true;}).length;}
  function filled(e){return pat(e).filter(Boolean).length;}
  function isDone(e){return e.cells.every(function(x){return inputs[key(x[0],x[1])].value===P.cells[x[0]][x[1]];});}

  function hint(e){ // deduced entry: constraint signal only, never the word
    if(filled(e)===0)return '<span class="hint">◇ needs crossings</span>';
    var n=fits(e);
    if(n===0)return '<span class="hint">◇ no word fits — a crossing is off</span>';
    if(n===1)return '<span class="one">◆ one word fits — deduce it</span>';
    return '<span class="hint">◇ '+n+' still fit</span>';
  }

  function render(){
    for(var r=0;r<R;r++)for(var c=0;c<C;c++){var cl=document.getElementById("cell-"+r+"-"+c);cl.classList.remove("inline","active");}
    var e=cur();
    if(e)e.cells.forEach(function(x){document.getElementById("cell-"+x[0]+"-"+x[1]).classList.add("inline");});
    if(active)document.getElementById("cell-"+active.r+"-"+active.c).classList.add("active");
    var cl=document.getElementById("curline");
    if(!e){cl.textContent="";return;}
    if(e.role==="given"){cl.className="curline given";cl.innerHTML='<b>'+e.label+'</b>'+esc(e.clue)+' <span style="color:var(--faint)">('+e.len+')</span>';}
    else{cl.className="curline deduced";cl.innerHTML='<b>'+e.label+'</b>'+hint(e)+' <span style="color:var(--faint)">('+e.len+')</span>';}
  }

  function buildList(list,elId){var ol=document.getElementById(elId);
    list.forEach(function(e){var li=document.createElement("li");li.id="li-"+e.dir+e.num;li.className=e.role;
      li.innerHTML='<span class="cn">'+e.num+'</span><span class="ct"></span>';li.addEventListener("click",function(){jump(e);});ol.appendChild(li);});}
  buildList(P.across,"acr");buildList(P.down,"dwn");

  function paint(e){var li=document.getElementById("li-"+e.dir+e.num);var ct=li.querySelector(".ct");
    if(e.role==="given")ct.innerHTML=esc(e.clue)+' <span style="color:var(--faint)">('+e.len+')</span>';
    else ct.innerHTML=hint(e)+' <span style="color:var(--faint)">('+e.len+')</span>';
    li.classList.toggle("done",isDone(e));li.classList.toggle("on",cur()===e);}

  // the thread: latent full path (faint) + live path through deduced entries solved in order
  var thread=P.thread; // [{label,cx,cy}] in forced-solve order
  document.getElementById("latent").setAttribute("points",thread.map(function(t){return t.cx+","+t.cy;}).join(" "));
  var nodesG=document.getElementById("nodes");
  thread.forEach(function(t){var ci=document.createElementNS("http://www.w3.org/2000/svg","circle");
    ci.setAttribute("cx",t.cx);ci.setAttribute("cy",t.cy);ci.setAttribute("r",".07");ci.setAttribute("class","node");ci.style.opacity=".28";ci.id="node-"+t.label;nodesG.appendChild(ci);});
  function entByLabel(lab){return all.find(function(x){return x.label===lab;});}
  var litSet={};
  function refreshThread(){
    var live=[],broke=false;
    for(var i=0;i<thread.length;i++){
      var lab=thread[i].label,ent=entByLabel(lab),node=document.getElementById("node-"+lab);
      if(!broke&&ent&&isDone(ent)){
        live.push(thread[i]);node.style.opacity="1";
        if(!litSet[lab]){ // newly deduced -> a domino flash
          litSet[lab]=true;
          ent.cells.forEach(function(x){var cl=document.getElementById("cell-"+x[0]+"-"+x[1]);cl.classList.add("lit","pop");setTimeout(function(){cl.classList.remove("pop");},560);});
        }else ent.cells.forEach(function(x){document.getElementById("cell-"+x[0]+"-"+x[1]).classList.add("lit");});
      }else{node.style.opacity=".28";broke=true;if(ent&&litSet[lab]){litSet[lab]=false;ent.cells.forEach(function(x){document.getElementById("cell-"+x[0]+"-"+x[1]).classList.remove("lit");});}}
    }
    document.getElementById("live").setAttribute("points",live.map(function(t){return t.cx+","+t.cy;}).join(" "));
  }

  var status=document.getElementById("status"),solvedOnce=false;
  function refresh(){
    P.across.forEach(paint);P.down.forEach(paint);render();refreshThread();
    var done=true;for(var r=0;r<R;r++)for(var c=0;c<C;c++)if(inputs[key(r,c)].value!==P.cells[r][c])done=false;
    if(done&&!solvedOnce){solvedOnce=true;win();}
  }
  function win(){
    status.textContent="Solved. Four clues carried ten answers.";
    var d=P.debrief;
    document.getElementById("debriefP").innerHTML="You were given <b>"+d.given+"</b> clues and deduced the other <b>"+d.deduced+"</b> from the grid alone, in a forced chain <b>"+d.depth+"</b> steps deep. The ice-breaker — the first answer with no clue you could crack — was <b>"+d.ice.label+" "+d.ice.answer+"</b>, pinned with only "+d.ice.vis+" of its 5 letters showing. The last domino, <b>"+d.last.label+" "+d.last.answer+"</b>, would not fall until everything else had.";
    var stats=[["Clues given",d.given,""],["Answers deduced",d.deduced,"hl"],["Cascade depth",d.depth+" deep",""],["First crack",d.ice.label+" · "+d.ice.vis+"/5","hl"],["Est. difficulty",d.rating,"hl"]];
    document.getElementById("stats").innerHTML=stats.map(function(s){return '<div class="stat '+s[2]+'"><div class="k">'+s[0]+'</div><div class="v">'+s[1]+'</div></div>';}).join("");
    document.getElementById("debrief").classList.add("show");
    document.getElementById("debrief").scrollIntoView({behavior:"smooth",block:"nearest"});
  }
  document.getElementById("clearBtn").addEventListener("click",function(){
    for(var r=0;r<R;r++)for(var c=0;c<C;c++){var inp=inputs[key(r,c)];inp.value="";inp.classList.remove("wrong");document.getElementById("cell-"+r+"-"+c).classList.remove("lit");}
    solvedOnce=false;document.getElementById("debrief").classList.remove("show");
    status.textContent="Cleared. Solve the four gold clues; the thread does the rest.";setActive(0,0,true);refresh();});

  function esc(s){var d=document.createElement("div");d.textContent=s;return d.innerHTML;}
  var f=null;for(var r=0;r<R&&!f;r++)for(var c=0;c<C&&!f;c++)f=[r,c];
  setActive(f[0],f[1],true);refresh();
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
