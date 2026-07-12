"""Build site/endogenous.html -- the 'half the clues' cascade mini (relational difficulty).

The demonstration behind docs/relational-difficulty.md, made playable. Only the five
information-floor entries are clued (model-written, Monday); the other five are *endogenous*
-- no trivia clue, recovered from the crossings. A browser-side candidate helper (the same
`n_candidates` primitive, over the >=50 vocabulary) makes the forcing visible: fill enough
crossing letters and exactly one word fits, so every derived answer is *deduced*, never known.

    uv run --extra clue python site/build_endogenous.py     # regenerate (one live clue call)

Deterministic grid (seed 9, cw fill >=88); the five seed clues are written live by the model
each run (like the rest of the gallery). Everything else -- floor, wave order, candidate lists
-- is computed by the relational model. Self-contained: writes one HTML file, no external assets.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from relational import _entries, information_floor, propagate  # noqa: E402

from puzzledesk.app.clue import ClueStyle, Difficulty  # noqa: E402
from puzzledesk.app.puzzle import filled_from_square  # noqa: E402
from puzzledesk.bootstrap import build  # noqa: E402
from puzzledesk.core.engines import backtrack  # noqa: E402
from puzzledesk.core.square import DoubleSquare  # noqa: E402

SEED = 9
FILL_BAR = 88.0  # the (fun, common) fill quality bar
VOCAB_BAR = 50.0  # the solver's assumed vocabulary -- also what the browser helper filters on
OUT = Path(__file__).resolve().parent / "endogenous.html"


def build_data() -> dict:
    c = build()
    full = c.lexicon.load("cw", 5)
    vocab = full.filtered(VOCAB_BAR)
    nc = lambda a, k: vocab.n_candidates(a, k)  # noqa: E731

    sq = DoubleSquare(full.filtered(FILL_BAR))
    state = backtrack.solve(sq, rng=c.rng_factory.create(SEED), distinct=True)
    if state is None:
        raise SystemExit("grid UNSAT at this bar/seed")
    grid = filled_from_square(sq, state)

    entries = _entries(grid)
    fset, fdepth = information_floor(entries, nc)
    prop = propagate(entries, set(fset), nc)

    # Model-written Monday clues for the seed entries only (the endogenous ones need none).
    seed_targets = [t for t in grid.runs() if t.id in fset]
    clued = c.clue.clue(grid, style=ClueStyle(difficulty=Difficulty.MONDAY), targets=seed_targets)
    clue_text = {tid: (cl.text if (cl := clued.clues.get(tid)) else "") for tid in fset}

    def entry_json(e):
        return {
            "num": int(e.label[:-1]),
            "dir": e.label[-1],
            "answer": e.answer.upper(),
            "len": len(e.cells),
            "cells": [[r, col] for (r, col) in e.cells],
            "role": "seed" if e.eid in fset else "derived",
            "clue": clue_text.get(e.eid, ""),
            "wave": prop.wave_of[e.eid],
        }

    ents_json = [entry_json(e) for e in entries]
    across = [e for e in ents_json if e["dir"] == "A"]
    down = [e for e in ents_json if e["dir"] == "D"]

    numbering = {f"{r},{col}": n for (r, col), n in grid.numbering().items()}
    cells = [[grid.cells[r][col].upper() for col in range(5)] for r in range(5)]

    waves = [
        [{"num": e["num"], "dir": e["dir"]} for e in ents_json if e["wave"] == w]
        for w in range(1, fdepth + 1)
    ]

    return {
        "rows": 5,
        "cols": 5,
        "cells": cells,
        "numbering": numbering,
        "across": across,
        "down": down,
        "floorDepth": fdepth,
        "floorSize": len(fset),
        "waves": waves,
        "vocab": sorted(w.upper() for w in vocab.words),  # length-5 candidate universe
        "vocabBar": VOCAB_BAR,
    }


def render(data: dict) -> str:
    payload = json.dumps(data, separators=(",", ":"))
    # thumbnail: 5x5 all-white with the five seed cells marked
    return (
        _TEMPLATE.replace("/*DATA*/", payload)
        .replace("<!--SEEDN-->", str(data["floorSize"]))
        .replace("<!--DEPTH-->", str(data["floorDepth"]))
        .replace("<!--VOCAB-->", str(int(data["vocabBar"])))
    )


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Half the Clues — puzzledesk</title>
<style>
:root{
  --bg:#ece9e2;--surface:#f7f5ef;--cell:#fcfbf7;--ink:#1b1915;--muted:#6c665b;
  --faint:#928b7d;--line:#cec9bd;--line-strong:#2a2620;--accent:#8f2734;
  --accent-ink:#7a1f2b;--accent-soft:rgba(143,39,52,.12);--good:#2f6b4f;
  --derive:#2c5f7a;--derive-soft:rgba(44,95,122,.12);
  --black:#2a2620;--sel-word:#e6f0fa;--sel-cell:#cfe4f7;--sel-line:#4a90d9;
  --serif:Georgia,"Iowan Old Style","Times New Roman",serif;
  --mono:ui-monospace,"SF Mono","Cascadia Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Helvetica,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#131210;--surface:#1d1b16;--cell:#232019;--ink:#ece6d9;--muted:#9a9384;
  --faint:#726c5f;--line:#35312a;--line-strong:#b8b0a0;--accent:#dd6b74;
  --accent-ink:#e78a90;--accent-soft:rgba(221,107,116,.16);--good:#74c299;
  --derive:#79b8d6;--derive-soft:rgba(121,184,214,.16);
  --black:#0c0b09;--sel-word:#26333f;--sel-cell:#33526b;--sel-line:#6ba7dd;
}}
:root[data-theme="light"]{
  --bg:#ece9e2;--surface:#f7f5ef;--cell:#fcfbf7;--ink:#1b1915;--muted:#6c665b;
  --faint:#928b7d;--line:#cec9bd;--line-strong:#2a2620;--accent:#8f2734;
  --accent-ink:#7a1f2b;--accent-soft:rgba(143,39,52,.12);--good:#2f6b4f;
  --derive:#2c5f7a;--derive-soft:rgba(44,95,122,.12);
  --black:#2a2620;--sel-word:#e6f0fa;--sel-cell:#cfe4f7;--sel-line:#4a90d9;
}
:root[data-theme="dark"]{
  --bg:#131210;--surface:#1d1b16;--cell:#232019;--ink:#ece6d9;--muted:#9a9384;
  --faint:#726c5f;--line:#35312a;--line-strong:#b8b0a0;--accent:#dd6b74;
  --accent-ink:#e78a90;--accent-soft:rgba(221,107,116,.16);--good:#74c299;
  --derive:#79b8d6;--derive-soft:rgba(121,184,214,.16);
  --black:#0c0b09;--sel-word:#26333f;--sel-cell:#33526b;--sel-line:#6ba7dd;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--serif);
  line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1000px;margin:0 auto;padding:36px 24px 72px}
a{color:var(--accent-ink)}
.masthead{border-bottom:3px double var(--line-strong);padding-bottom:18px;margin-bottom:8px}
.eyebrow{font-family:var(--sans);font-size:11px;letter-spacing:.22em;text-transform:uppercase;
  color:var(--muted);display:flex;justify-content:space-between;align-items:baseline;
  flex-wrap:wrap;gap:8px}
.eyebrow .day{color:var(--derive);font-weight:700}
.eyebrow a{color:var(--muted);text-decoration:none}
.eyebrow a:hover{color:var(--accent)}
h1{font-family:var(--serif);font-weight:700;font-size:clamp(32px,6.4vw,54px);line-height:.98;
  letter-spacing:-.02em;margin:10px 0 6px;text-wrap:balance}
.dek{font-size:16px;color:var(--muted);max-width:64ch;font-style:italic}
.dek b{color:var(--ink);font-style:normal;font-weight:700}
.theme-toggle{font-family:var(--sans);font-size:11px;letter-spacing:.08em;text-transform:uppercase;
  background:none;border:1px solid var(--line);color:var(--muted);padding:5px 11px;
  border-radius:2px;cursor:pointer}
.theme-toggle:hover{border-color:var(--accent);color:var(--accent)}
.play{display:grid;grid-template-columns:auto 1fr;gap:40px;margin-top:30px;align-items:start}
@media (max-width:720px){.play{grid-template-columns:1fr;gap:26px}}
.board-col{display:flex;flex-direction:column;gap:14px}
.grid{display:grid;width:min(360px,86vw);aspect-ratio:1;background:var(--line-strong);
  border:3px solid var(--line-strong);gap:1px;touch-action:manipulation;
  grid-template-columns:repeat(5,1fr);grid-template-rows:repeat(5,1fr)}
.cell{position:relative;background:var(--cell);min-width:0;min-height:0}
.cell .num{position:absolute;top:1px;left:2px;font-family:var(--mono);font-size:10px;
  color:var(--faint);line-height:1;pointer-events:none}
.cell input{width:100%;height:100%;border:0;background:transparent;text-align:center;
  font-family:var(--mono);font-weight:600;color:var(--ink);text-transform:uppercase;
  caret-color:transparent;padding:0;font-size:clamp(16px,5.2vw,26px)}
.cell input:focus{outline:none}
.cell.inline{background:var(--sel-word)}
.cell.active{background:var(--sel-cell);box-shadow:inset 0 0 0 2px var(--sel-line)}
.cell input.revealed{color:var(--accent)}
.cell input.wrong{color:var(--accent);text-decoration:line-through;text-decoration-color:var(--accent)}
.cell.forced{animation:pop .5s ease}
@keyframes pop{0%{background:var(--derive-soft)}40%{background:var(--derive);box-shadow:inset 0 0 0 2px var(--derive)}100%{}}
.controls{display:flex;gap:8px;flex-wrap:wrap}
.btn{font-family:var(--sans);font-size:12px;letter-spacing:.04em;padding:8px 14px;
  border-radius:3px;cursor:pointer;border:1px solid var(--line);background:var(--surface);color:var(--ink)}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{background:var(--accent-ink);color:#fff}
.btn.derive{border-color:var(--derive);color:var(--derive)}
.btn.derive:hover{background:var(--derive);color:#fff}
.status{font-family:var(--sans);font-size:12.5px;color:var(--muted);min-height:16px}
.status.win{color:var(--good);font-weight:600}
.curclue{font-family:var(--sans);font-size:14px;color:var(--ink);background:var(--surface);
  border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:3px;
  padding:9px 12px;min-height:20px}
.curclue.derived{border-left-color:var(--derive)}
.curclue b{color:var(--accent);font-weight:700;margin-right:6px}
.curclue.derived b{color:var(--derive)}
.curclue .cand{cursor:pointer;color:var(--derive);font-weight:700}
.curclue .cand:hover{text-decoration:underline}
.clues{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-content:start}
@media (max-width:560px){.clues{grid-template-columns:1fr}}
.clues h2{font-family:var(--sans);font-size:12px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--accent);margin:0 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line);
  display:flex;justify-content:space-between}
.clues h2 .leg{color:var(--derive);letter-spacing:.02em}
ol.clue-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:2px}
.clue-list li{display:grid;grid-template-columns:22px 1fr;gap:8px;font-size:14px;
  padding:5px 7px;border-radius:3px;cursor:pointer;align-items:baseline}
.clue-list li:hover{background:var(--accent-soft)}
.clue-list li.on{background:var(--accent-soft)}
.clue-list li.derived.on{background:var(--derive-soft)}
.clue-list li.done .ct{color:var(--faint)}
.clue-list li .cn{font-family:var(--mono);font-size:12px;color:var(--muted);text-align:right;font-weight:600}
.clue-list li.on .cn{color:var(--accent)}
.clue-list li.derived .ct{color:var(--derive)}
.clue-list li.derived .ct .hint{font-family:var(--mono);font-size:12px;color:var(--faint)}
.clue-list li.derived .ct .forced{color:var(--derive);font-weight:700;cursor:pointer}
.clue-list li.derived .ct .forced:hover{text-decoration:underline}
.note{margin-top:44px;border-top:3px double var(--line-strong);padding-top:22px}
.note .kicker{font-family:var(--sans);font-size:11px;letter-spacing:.22em;text-transform:uppercase;
  color:var(--muted);margin-bottom:6px}
.note h3{font-family:var(--serif);font-weight:700;font-size:22px;margin:0 0 8px;letter-spacing:-.01em}
.note p{margin:0 0 12px;font-size:15px;color:var(--muted);max-width:74ch}
.note p b{color:var(--ink)}
.note code{font-family:var(--mono);font-size:12.5px;background:var(--accent-soft);
  padding:1px 6px;border-radius:3px;color:var(--ink)}
.colophon{margin-top:38px;padding-top:16px;border-top:1px solid var(--line);
  font-family:var(--sans);font-size:12px;color:var(--faint);line-height:1.6}
.colophon a{color:var(--faint)}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <div class="eyebrow">
      <span>5×5 · <span class="day">Endogenous</span> · <!--SEEDN--> clues given, 5 forced by the grid</span>
      <span><a href="index.html">← all samples</a> &nbsp; <button class="theme-toggle" id="themeBtn" type="button">Theme</button></span>
    </div>
    <h1>Half the Clues</h1>
    <p class="dek">Only <b>five</b> of the ten entries have a clue. The other five have <b>none</b> — you recover them from the crossings alone. The grid carries the solve; difficulty is inference depth, not trivia.</p>
  </header>

  <section class="play">
    <div class="board-col">
      <div class="grid" id="grid" role="group" aria-label="Crossword grid"></div>
      <div class="curclue" id="curclue"></div>
      <div class="controls">
        <button class="btn primary" id="checkBtn" type="button">Check</button>
        <button class="btn derive" id="cascadeBtn" type="button">Watch it cascade</button>
        <button class="btn" id="clearBtn" type="button">Clear</button>
      </div>
      <div class="status" id="status" aria-live="polite">Solve the five given clues. Their letters force the other five — the clue line shows when only one word fits.</div>
    </div>
    <div class="clues">
      <div><h2>Across <span class="leg">◇ = forced</span></h2><ol class="clue-list" id="acrossClues"></ol></div>
      <div><h2>Down <span class="leg">◇ = forced</span></h2><ol class="clue-list" id="downClues"></ol></div>
    </div>
  </section>

  <section class="note">
    <div class="kicker">What you just played</div>
    <h3>Difficulty is relational</h3>
    <p>A dense mini is <b>over-determined</b>: every letter is checked twice, so most answers are pinned by their crossings whether or not they have a clue. This grid's <b>information floor</b> is five — five well-chosen clues are enough, and the crossings <em>force</em> the other five, in a six-wave cascade the model computes before a single clue is written. The maximally hard word is the one with a useless clue; it becomes gettable only because its neighbours donate letters. That is the whole lemma: a word's difficulty is not intrinsic, it is where it sits in the crossing graph.</p>
    <p>The five blank entries are <b>endogenous clues</b> — the answer comes from the puzzle's own logic, not outside knowledge. The “◇ N fit” hint is the browser running the same <code>n_candidates</code> check the solver model uses: fill enough crossings and exactly one word remains. No Natick, because the page proves each answer is forced. Full write-up: <code>docs/relational-difficulty.md</code>.</p>
  </section>

  <p class="colophon">
    puzzledesk · grid by the engines (<code>seed 9</code>, cw ≥ 88); the five seed clues written live by the model;
    the five forced answers checked against the score ≥ <!--VOCAB--> vocabulary in your browser — nothing stored.
    <a href="index.html">back to the gallery</a>.
  </p>
</div>
<script>var DATA=/*DATA*/;</script>
<script>
(function(){
  var P=DATA, R=P.rows, C=P.cols;
  var byDir={A:P.across,D:P.down};
  var all=P.across.concat(P.down);
  var mapA={},mapD={},numAt={},entByRef={};
  function key(r,c){return r+","+c;}
  byDir.A.forEach(function(e){entByRef["A"+e.num]=e;e.cells.forEach(function(x){mapA[key(x[0],x[1])]=e;});});
  byDir.D.forEach(function(e){entByRef["D"+e.num]=e;e.cells.forEach(function(x){mapD[key(x[0],x[1])]=e;});});
  for(var k in P.numbering)numAt[k]=P.numbering[k];
  var VOCAB=P.vocab;

  var grid=document.getElementById("grid");
  var inputs={},active=null,dir="A";
  for(var r=0;r<R;r++)for(var c=0;c<C;c++){
    var cell=document.createElement("div");
    cell.className="cell";
    cell.id="cell-"+r+"-"+c;
    var n=numAt[key(r,c)];
    if(n){var s=document.createElement("span");s.className="num";s.textContent=n;cell.appendChild(s);}
    var inp=document.createElement("input");
    inp.type="text";inp.maxLength=1;inp.inputMode="text";inp.autocapitalize="characters";
    inp.setAttribute("aria-label","row "+(r+1)+" column "+(c+1));
    (function(r,c,inp){
      inp.addEventListener("focus",function(){setActive(r,c,false);});
      inp.addEventListener("mousedown",function(){if(active&&active.r===r&&active.c===c)dir=(dir==="A"?"D":"A");});
      inp.addEventListener("input",function(){
        inp.value=(inp.value||"").toUpperCase().replace(/[^A-Z]/g,"");
        inp.classList.remove("revealed","wrong");
        if(inp.value)step(1);
        refresh();
      });
      inp.addEventListener("keydown",function(e){
        var k=e.key;
        if(k==="Backspace"){
          if(!inp.value){step(-1);var p=inputs[key(active.r,active.c)];if(p){p.value="";p.classList.remove("revealed","wrong");}e.preventDefault();refresh();}
          else{inp.classList.remove("revealed","wrong");}
        }else if(k==="ArrowRight"){dir="A";nudge(0,1);e.preventDefault();}
        else if(k==="ArrowLeft"){dir="A";nudge(0,-1);e.preventDefault();}
        else if(k==="ArrowDown"){dir="D";nudge(1,0);e.preventDefault();}
        else if(k==="ArrowUp"){dir="D";nudge(-1,0);e.preventDefault();}
        else if(k===" "){dir=(dir==="A"?"D":"A");render();e.preventDefault();}
        else if(k==="Tab"){cycleEntry(e.shiftKey?-1:1);e.preventDefault();}
      });
    })(r,c,inp);
    cell.appendChild(inp);grid.appendChild(cell);inputs[key(r,c)]=inp;
  }

  function curEntry(){var e=(dir==="A"?mapA:mapD)[key(active.r,active.c)];return e||(dir==="A"?mapD:mapA)[key(active.r,active.c)];}
  function setActive(r,c,focus){active={r:r,c:c};if(focus!==false){var el=inputs[key(r,c)];if(el)el.focus();}render();}
  function nudge(dr,dc){var nr=active.r+dr,nc=active.c+dc;while(nr>=0&&nc>=0&&nr<R&&nc<C){setActive(nr,nc,true);return;}}
  function step(s){var e=curEntry();if(!e)return;for(var i=0;i<e.cells.length;i++){if(e.cells[i][0]===active.r&&e.cells[i][1]===active.c){var j=i+s;if(j>=0&&j<e.cells.length)setActive(e.cells[j][0],e.cells[j][1],true);return;}}}
  function cycleEntry(s){var list=byDir[dir];var e=curEntry();var idx=list.indexOf(e);var nx=list[(idx+s+list.length)%list.length];jumpTo(nx);}
  function jumpTo(e){var t=e.cells.find(function(x){return !inputs[key(x[0],x[1])].value;})||e.cells[0];dir=e.dir;setActive(t[0],t[1],true);}

  // the browser n_candidates: words matching an entry's currently-typed letters
  function pattern(e){return e.cells.map(function(x){return inputs[key(x[0],x[1])].value||"";});}
  function candidates(e){
    var pat=pattern(e);
    return VOCAB.filter(function(w){
      if(w.length!==e.len)return false;
      for(var i=0;i<pat.length;i++){if(pat[i]&&w[i]!==pat[i])return false;}
      return true;
    });
  }
  function filledCount(e){return pattern(e).filter(Boolean).length;}

  function placeWord(e,w){
    e.cells.forEach(function(x,i){var inp=inputs[key(x[0],x[1])];inp.value=w[i];inp.classList.remove("wrong","revealed");
      var cell=document.getElementById("cell-"+x[0]+"-"+x[1]);cell.classList.add("forced");setTimeout(function(){cell.classList.remove("forced");},520);});
    refresh();
  }

  function deriveHint(e){
    // returns {text, forced:word|null}
    if(e.role==="seed")return null;
    var cs=candidates(e);
    if(filledCount(e)===0)return {html:'<span class="hint">◇ derive from the grid</span>',forced:null};
    if(cs.length===0)return {html:'<span class="hint">◇ no word fits — a crossing is off</span>',forced:null};
    if(cs.length===1)return {html:'◆ forced → <span class="forced" data-w="'+cs[0]+'">'+cs[0]+'</span>',forced:cs[0]};
    if(cs.length<=6)return {html:'<span class="hint">◇ '+cs.length+' fit: '+cs.join(", ")+'</span>',forced:null};
    return {html:'<span class="hint">◇ '+cs.length+' words fit — get more crossings</span>',forced:null};
  }

  function render(){
    for(var r=0;r<R;r++)for(var c=0;c<C;c++){var cell=document.getElementById("cell-"+r+"-"+c);cell.classList.remove("active","inline");}
    var e=curEntry();
    if(e)e.cells.forEach(function(x){document.getElementById("cell-"+x[0]+"-"+x[1]).classList.add("inline");});
    if(active)document.getElementById("cell-"+active.r+"-"+active.c).classList.add("active");
    var cur=document.getElementById("curclue");
    if(!e){cur.textContent="";return;}
    if(e.role==="seed"){
      cur.className="curclue";
      cur.innerHTML='<b>'+e.num+e.dir+'</b>'+esc(e.clue)+' <span style="color:var(--faint)">('+e.len+')</span>';
    }else{
      cur.className="curclue derived";
      var h=deriveHint(e);
      cur.innerHTML='<b>'+e.num+e.dir+'</b>'+h.html+' <span style="color:var(--faint)">('+e.len+')</span>';
      wireForced(cur,e);
    }
  }
  function wireForced(container,e){
    var el=container.querySelector(".forced,.cand");
    if(el)el.addEventListener("click",function(){placeWord(e,el.getAttribute("data-w"));});
  }

  function buildClues(list,elId,tag){
    var ol=document.getElementById(elId);
    list.forEach(function(e){
      var li=document.createElement("li");li.id="clue-"+tag+e.num;
      li.className=(e.role==="derived"?"derived":"");
      li.innerHTML='<span class="cn">'+e.num+'</span><span class="ct"></span>';
      li.addEventListener("click",function(){jumpTo(e);});
      ol.appendChild(li);
    });
  }
  buildClues(byDir.A,"acrossClues","A");
  buildClues(byDir.D,"downClues","D");

  function paintClue(e,tag){
    var li=document.getElementById("clue-"+tag+e.num);if(!li)return;
    var ct=li.querySelector(".ct");
    if(e.role==="seed"){ct.innerHTML=esc(e.clue)+' <span style="color:var(--faint)">('+e.len+')</span>';}
    else{var h=deriveHint(e);ct.innerHTML=h.html+' <span style="color:var(--faint)">('+e.len+')</span>';
      var f=ct.querySelector(".forced");if(f)f.addEventListener("click",function(ev){ev.stopPropagation();placeWord(e,f.getAttribute("data-w"));});}
    var full=e.cells.every(function(x){return inputs[key(x[0],x[1])].value===P.cells[x[0]][x[1]];});
    li.classList.toggle("done",full);
    li.classList.toggle("on",curEntry()===e);
  }

  var status=document.getElementById("status");
  function refresh(){
    byDir.A.forEach(function(e){paintClue(e,"A");});
    byDir.D.forEach(function(e){paintClue(e,"D");});
    render();
    checkWin();
  }
  function checkWin(){
    var done=true;
    for(var r=0;r<R;r++)for(var c=0;c<C;c++){if(inputs[key(r,c)].value!==P.cells[r][c])done=false;}
    if(done){status.textContent="Solved from five clues — the grid carried the rest.";status.className="status win";}
  }

  document.getElementById("checkBtn").addEventListener("click",function(){
    var filled=0,wrong=0,total=0;
    for(var r=0;r<R;r++)for(var c=0;c<C;c++){total++;var inp=inputs[key(r,c)];if(inp.value){filled++;if(inp.value!==P.cells[r][c]){inp.classList.add("wrong");wrong++;}else inp.classList.remove("wrong");}}
    if(filled===0)status.textContent="Fill the given clues first.";
    else if(wrong===0&&filled===total){status.textContent="Solved from five clues — the grid carried the rest.";status.className="status win";return;}
    else if(wrong===0)status.textContent="So far so good — "+(total-filled)+" to go.";
    else status.textContent=wrong+" square"+(wrong>1?"s":"")+" off.";
    status.className=(wrong?"status":"status");
  });
  document.getElementById("clearBtn").addEventListener("click",function(){
    for(var r=0;r<R;r++)for(var c=0;c<C;c++){var inp=inputs[key(r,c)];inp.value="";inp.classList.remove("wrong","revealed");}
    status.textContent="Cleared. Solve the five given clues; the rest follow.";status.className="status";
    setActive(0,0,true);refresh();
  });

  // The cascade: clear, then reveal wave by wave (seeds first), showing the grid unzip.
  var cascading=false;
  document.getElementById("cascadeBtn").addEventListener("click",function(){
    if(cascading)return;cascading=true;
    for(var r=0;r<R;r++)for(var c=0;c<C;c++){var inp=inputs[key(r,c)];inp.value="";inp.classList.remove("wrong","revealed");}
    refresh();
    var waves=P.waves,i=0;
    function fillEntry(ref){var e=entByRef[ref.dir+ref.num];placeWord(e,e.answer);}
    function nextWave(){
      if(i>=waves.length){status.textContent="Five given clues (wave 1) forced the other five over "+waves.length+" waves.";status.className="status win";cascading=false;return;}
      var w=waves[i];
      w.forEach(fillEntry);
      var names=w.map(function(x){return x.num+x.dir;}).join(", ");
      status.textContent=(i===0?"Wave 1 — the five given clues: ":"Wave "+(i+1)+" — forced by crossings: ")+names;
      status.className="status";
      i++;setTimeout(nextWave,i===1?900:1200);
    }
    setTimeout(nextWave,300);
  });

  function esc(s){var d=document.createElement("div");d.textContent=s;return d.innerHTML;}
  var root=document.documentElement;
  document.getElementById("themeBtn").addEventListener("click",function(){
    var cur=root.getAttribute("data-theme");
    if(!cur)cur=window.matchMedia("(prefers-color-scheme:dark)").matches?"dark":"light";
    root.setAttribute("data-theme",cur==="dark"?"light":"dark");
  });

  setActive(0,0,true);refresh();
})();
</script>
</body>
</html>
"""


def main() -> None:
    data = build_data()
    OUT.write_text(render(data), encoding="utf-8")
    seeds = [f"{e['num']}{e['dir']}" for e in data["across"] + data["down"] if e["role"] == "seed"]
    print(f"wrote {OUT}  ({OUT.stat().st_size // 1024} KB)")
    print(f"seed clues: {seeds}  floor depth {data['floorDepth']}  vocab {len(data['vocab'])} words")
    for e in data["across"] + data["down"]:
        tag = "seed " if e["role"] == "seed" else "DERIV"
        print(f"  {tag} {e['num']}{e['dir']} {e['answer']}  w{e['wave']}  {html.unescape(e['clue'])}")


if __name__ == "__main__":
    main()
