"""Build site/endogenous.html -- the 'half the clues' cascade mini (relational difficulty).

The demonstration behind docs/relational-difficulty.md, made playable. Only the
information-floor entries are clued (model-written, Monday); the rest are *endogenous* --
no trivia clue, recovered from the crossings. A browser-side candidate helper (the same
`n_candidates` primitive, over the >=50 vocabulary) makes the forcing visible: it reports how
many words still fit, and when exactly one does it says so *without naming it* -- the player
deduces the word from its letter-pattern.

That deduction is a THIRD difficulty axis (docs/relational-difficulty.md): not word obscurity
(the project's original framing -- a fairness cliff, D9/D26) and not clue obliqueness (the
dominant fair axis when clues exist, D26), but *retrievability from a partial pattern*. A
pattern like ``..CYS`` is lexically maximally precise (one word fits: MACYS) yet humanly
imprecise -- you cannot enumerate the survivor, especially a proper noun. So the grid is chosen
to keep the letter-clue *humanly* precise: every entry is a common dictionary word, and the
difficulty knob is ``minvis`` -- the fewest letters showing when a word is forced (5 = read it
off, 4 = a gentle one-blank recall, 3 = a real two-blank deduction).

    uv run --extra clue python site/build_endogenous.py     # regenerate both pages (two clue calls)

It emits TWO puzzles from one player, differing only by a small spec (the "which entries are
clueless" rule + copy): ``endogenous.html`` (the information floor -- clue the minimum, the
crossings force the rest in a cascade) and ``keystone.html`` (a designed clueless set -- clue all
but the central cross, leaving one deduced cell at dead centre). Grids are chosen by a reproducible
search; the seed clues are written live by the model each run (like the rest of the gallery).
Everything else -- floor/cascade, wave order, deduction profile -- is computed by the relational
model. Self-contained: writes two HTML files, no external assets.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from puzzledesk.app.clue import ClueStyle, Difficulty
from puzzledesk.app.puzzle import filled_from_square
from puzzledesk.bootstrap import build
from puzzledesk.core.engines import backtrack
from puzzledesk.core.square import DoubleSquare
from relational import Entry, _entries, information_floor, propagate

TARGET_MINVIS = {"monday": 4, "wednesday": 3}  # min letters showing at a forcing, per difficulty
FILL_BAR = 90.0  # the fill quality bar (all-common grids come from the top tier)
VOCAB_BAR = 50.0  # the solver's assumed vocabulary -- also what the browser helper filters on
COMMON_ZIPF = 3.2  # every entry at least this frequent -> retrievable, no obscure words
MIN_DEPTH = 4  # a genuine multi-wave cascade, not the degenerate one-direction floor
CENTER = (2, 2)  # the keystone: where 3-Down and the central Across meet on a full 5x5
KEYSTONE_CLUELESS = frozenset({((0, 2), "D"), ((2, 0), "A")})  # 3D + central Across (7A)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SITE_DIR = Path(__file__).resolve().parent


def _oracles() -> tuple[set[str], dict[str, float]]:
    """Retrievability oracles: a plain dictionary (proper nouns/slang are *out*) and a
    word-frequency map (wordfreq Zipf), both length-5. A derived answer must be a common
    dictionary word so it is deducible from its pattern, not just lexically forced."""
    dictw = {w.strip().lower() for w in (DATA_DIR / "words_5.txt").read_text().splitlines()}
    scored: dict[str, float] = {}
    for line in (DATA_DIR / "scored_5.txt").read_text().splitlines():
        parts = line.split()
        if len(parts) == 2:
            scored[parts[0]] = float(parts[1])
    return dictw, scored


def _deduction_profile(entries: list[Entry], clued: frozenset, nc) -> list[tuple] | None:
    """Replay the cascade and, for each *clueless* entry in solve order, record how many of
    its letters were already showing at the moment it became forced. Fewer letters = a harder
    retrieval (the deduction-difficulty axis). None if it deadlocks."""
    known: set[tuple[int, int]] = set()
    solved: set = set()
    prof: list[tuple] = []
    while len(solved) < len(entries):
        newly = [
            e
            for e in entries
            if e.eid not in solved
            and (
                e.eid in clued
                or nc(e.answer, frozenset(i for i, cc in enumerate(e.cells) if cc in known)) == 1
            )
        ]
        if not newly:
            return None
        for e in newly:
            if e.eid not in clued:
                prof.append((e.label, e.answer.upper(), sum(1 for cc in e.cells if cc in known)))
        for e in newly:
            solved.add(e.eid)
            known.update(e.cells)
    return prof


def _all_common(entries: list[Entry], dictw, scored) -> bool:
    """Every entry a common dictionary word -> every answer is retrievable from a pattern."""
    return all(e.answer in dictw and scored.get(e.answer, 0) >= COMMON_ZIPF for e in entries)


def _grids(c, full):
    """Iterate distinct top-tier double squares (deterministic seed order)."""
    sq = DoubleSquare(full.filtered(FILL_BAR))
    for seed in range(30000):
        state = backtrack.solve(sq, rng=c.rng_factory.create(seed), distinct=True)
        if state is not None:
            yield seed, filled_from_square(sq, state)


def _select_floor(c, full, nc, dictw, scored, spec, avoid):
    """The 'information floor' puzzle: clue the minimum set; the crossings force the rest, at
    a chosen deduction difficulty (the hardest forcing still shows TARGET_MINVIS letters)."""
    target = TARGET_MINVIS[spec["difficulty"]]
    for seed, grid in _grids(c, full):
        entries = _entries(grid)
        if not _all_common(entries, dictw, scored):
            continue
        floor = information_floor(entries, nc)
        if floor is None:
            continue
        clued, fdepth = floor
        prof = _deduction_profile(entries, clued, nc)
        if prof is None or fdepth < MIN_DEPTH or min(v for *_, v in prof) != target:
            continue
        return seed, grid, entries, clued
    raise SystemExit("no floor grid matched the fairness + difficulty filter")


def _select_keystone(c, full, nc, dictw, scored, spec, avoid):
    """The 'keystone' puzzle: clue every entry EXCEPT the central cross (3-Down and the
    central Across). Every square is then given but their intersection -- one unclued cell at
    dead centre, recovered from the two crossing words.

    Only the *clueless* pair must be retrievable (common dictionary words) -- the eight clued
    entries just need to be real words a clue can name. That is the general rule for a
    designated-clueless puzzle: retrievability is required only where the clue is withheld."""
    for seed, grid in _grids(c, full):
        entries = _entries(grid)
        if not all(e.answer in dictw for e in entries):  # every entry clueable (a real word)
            continue
        if frozenset(e.answer for e in entries) == avoid:  # keep it distinct from the floor page
            continue
        central = [e for e in entries if e.eid in KEYSTONE_CLUELESS]
        if len(central) != 2 or not _all_common(central, dictw, scored):
            continue  # the two deduced words must be retrievable from their pattern
        clued = frozenset(e.eid for e in entries if e.eid not in KEYSTONE_CLUELESS)
        if propagate(entries, set(clued), nc).solved:
            return seed, grid, entries, clued
    raise SystemExit("no keystone grid matched")


_SELECTORS = {"floor": _select_floor, "keystone": _select_keystone}


def build_data(spec: dict, avoid: frozenset = frozenset()) -> dict:
    c = build()
    full = c.lexicon.load("cw", 5)
    vocab = full.filtered(VOCAB_BAR)
    nc = lambda a, k: vocab.n_candidates(a, k)  # noqa: E731
    dictw, scored = _oracles()

    seed, grid, entries, clued = _SELECTORS[spec["select"]](c, full, nc, dictw, scored, spec, avoid)
    prop = propagate(entries, set(clued), nc)
    fdepth = prop.depth
    prof = _deduction_profile(entries, clued, nc) or []
    minvis = min((v for *_, v in prof), default=5)

    # Model-written Monday clues for the CLUED entries only (the clueless ones need none).
    clued_targets = [t for t in grid.runs() if t.id in clued]
    res = c.clue.clue(grid, style=ClueStyle(difficulty=Difficulty.MONDAY), targets=clued_targets)
    clue_text = {tid: (cl.text if (cl := res.clues.get(tid)) else "") for tid in clued}

    def entry_json(e: Entry) -> dict:
        return {
            "num": int(e.label[:-1]),
            "dir": e.label[-1],
            "answer": e.answer.upper(),
            "len": len(e.cells),
            "cells": [[r, col] for (r, col) in e.cells],
            "role": "seed" if e.eid in clued else "derived",
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
        "floorSize": len(clued),
        "derivedN": len(entries) - len(clued),
        "minvis": minvis,
        "seed": seed,
        "profile": prof,
        "waves": waves,
        "keystone": list(CENTER) if spec["select"] == "keystone" else None,
        "vocab": sorted(w.upper() for w in vocab.words),  # length-5 candidate universe
        "vocabBar": VOCAB_BAR,
    }


def render(data: dict, copy: dict) -> str:
    payload = json.dumps(data, separators=(",", ":"))
    page = _TEMPLATE
    for tok in ("TITLE", "DAY", "EYEBROW", "DEK", "NOTE"):
        page = page.replace(f"<!--{tok}-->", copy[tok.lower()])
    page = page.replace("/*DATA*/", payload)
    for tok, val in (
        ("SEEDN", data["floorSize"]),
        ("DERIVEDN", data["derivedN"]),
        ("DEPTH", data["floorDepth"]),
        ("MINVIS", data["minvis"]),
        ("VOCAB", int(data["vocabBar"])),
    ):
        page = page.replace(f"<!--{tok}-->", str(val))
    return page


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title><!--TITLE--> — puzzledesk</title>
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
.cell.keystone::after{content:"";position:absolute;inset:3px;border:2px dashed var(--derive);
  border-radius:3px;pointer-events:none}
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
.one{color:var(--derive);font-weight:700}
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
.clue-list li.derived .ct .one{color:var(--derive);font-weight:700}
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
      <span>5×5 · <span class="day"><!--DAY--></span> · <!--EYEBROW--></span>
      <span><a href="index.html">← all samples</a> &nbsp; <button class="theme-toggle" id="themeBtn" type="button">Theme</button></span>
    </div>
    <h1><!--TITLE--></h1>
    <p class="dek"><!--DEK--></p>
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
      <div class="status" id="status" aria-live="polite">Solve the given clues. Their letters constrain the blank entries — when a line reads ◆ one word fits, you have enough to work it out. No word is ever given away.</div>
    </div>
    <div class="clues">
      <div><h2>Across <span class="leg">◇ no clue · ◆ deducible</span></h2><ol class="clue-list" id="acrossClues"></ol></div>
      <div><h2>Down <span class="leg">◇ no clue · ◆ deducible</span></h2><ol class="clue-list" id="downClues"></ol></div>
    </div>
  </section>

  <section class="note">
    <!--NOTE-->
  </section>

  <p class="colophon">
    puzzledesk · grid by the engines (top-tier fill, all common words); the <!--SEEDN--> seed clues written live by the model;
    the <!--DERIVEDN--> forced answers checked against the score ≥ <!--VOCAB--> vocabulary in your browser — nothing stored.
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
    if(P.keystone&&P.keystone[0]===r&&P.keystone[1]===c)cell.classList.add("keystone");
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
    // A constraint signal only -- never the word. The player deduces it.
    if(e.role==="seed")return "";
    var n=candidates(e).length, fc=filledCount(e);
    if(fc===0)return '<span class="hint">◇ no crossings yet</span>';
    if(n===0)return '<span class="hint">◇ no word fits — a crossing is off</span>';
    if(n===1)return '<span class="one">◆ one word fits — deduce it</span>';
    return '<span class="hint">◇ '+n+' words still fit</span>';
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
      cur.innerHTML='<b>'+e.num+e.dir+'</b>'+deriveHint(e)+' <span style="color:var(--faint)">('+e.len+')</span>';
    }
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
    else{ct.innerHTML=deriveHint(e)+' <span style="color:var(--faint)">('+e.len+')</span>';}
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
    if(done){status.textContent="Solved from "+P.floorSize+" clues — the grid carried the rest.";status.className="status win";}
  }

  document.getElementById("checkBtn").addEventListener("click",function(){
    var filled=0,wrong=0,total=0;
    for(var r=0;r<R;r++)for(var c=0;c<C;c++){total++;var inp=inputs[key(r,c)];if(inp.value){filled++;if(inp.value!==P.cells[r][c]){inp.classList.add("wrong");wrong++;}else inp.classList.remove("wrong");}}
    if(filled===0)status.textContent="Fill the given clues first.";
    else if(wrong===0&&filled===total){status.textContent="Solved from "+P.floorSize+" clues — the grid carried the rest.";status.className="status win";return;}
    else if(wrong===0)status.textContent="So far so good — "+(total-filled)+" to go.";
    else status.textContent=wrong+" square"+(wrong>1?"s":"")+" off.";
    status.className=(wrong?"status":"status");
  });
  document.getElementById("clearBtn").addEventListener("click",function(){
    for(var r=0;r<R;r++)for(var c=0;c<C;c++){var inp=inputs[key(r,c)];inp.value="";inp.classList.remove("wrong","revealed");}
    status.textContent="Cleared. Solve the "+P.floorSize+" given clues; the rest follow.";status.className="status";
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
      if(i>=waves.length){status.textContent=P.floorSize+" given clues (wave 1) forced the other "+P.derivedN+" over "+waves.length+" waves.";status.className="status win";cascading=false;return;}
      var w=waves[i];
      w.forEach(fillEntry);
      var names=w.map(function(x){return x.num+x.dir;}).join(", ");
      status.textContent=(i===0?"Wave 1 — the given clues: ":"Wave "+(i+1)+" — forced by crossings: ")+names;
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


# The two puzzles: same player, different "which entries are clueless" rule + copy. Making
# that rule a spec is the point -- composing where the deduction lives is a design choice.
_FLOOR_NOTE = """<div class="kicker">What you just played</div>
    <h3>Difficulty is relational — and a third kind of hard</h3>
    <p>A dense mini is <b>over-determined</b>: every letter is checked twice, so most answers are pinned by their crossings whether or not they have a clue. This grid's <b>information floor</b> is <!--SEEDN--> — <!--SEEDN--> well-chosen clues are enough, and the crossings <em>force</em> the other <!--DERIVEDN-->, in a <!--DEPTH-->-wave cascade the model computes before a clue is written. A word's difficulty is not intrinsic: it is where it sits in the crossing graph, and what its neighbours donate.</p>
    <p>Strip the clue and a <b>third difficulty axis</b> appears — distinct from the two this project already mapped. Not <b>word obscurity</b> (do you know the word — a fairness cliff, not a slope) and not <b>clue obliqueness</b> (how vague the definition — the dominant fair axis when clues exist), but <b>retrievability from a pattern</b>: with the clue gone, the answer's own letters are the clue, and the question is whether you can <em>produce</em> the word from them. A pattern can be <em>lexically</em> forced (one word fits) yet <em>humanly</em> hard — <code>··CYS</code> uniquely forces MACYS, but you can't enumerate that. So this grid is tuned to keep the letter-clue humanly fair: every answer is a common word, forced with at least <b><!--MINVIS--></b> of its <b>5</b> letters showing — that <code>minvis</code> is the knob.</p>
    <p>The “◇ N still fit” counter is the browser running the same <code>n_candidates</code> check the solver model uses; when it drops to <b>◆ one word fits</b>, the pattern is uniquely determined and it is <em>yours to deduce</em> — the page never names it. You are told <em>when</em> a slot is solvable, never <em>what</em> it is: no Natick, no giveaway. Companion puzzle: <a href="keystone.html">The Keystone</a>. Full write-up: <code>docs/relational-difficulty.md</code>.</p>"""

_KEYSTONE_NOTE = """<div class="kicker">What you just played</div>
    <h3>Composing where the deduction lives</h3>
    <p>Once the no-clue solve is <em>explicit</em>, <b>which</b> entries you leave clueless becomes a design choice with its own aesthetic. Here the choice is deliberate: clue all eight perimeter entries and blank only the two that meet in the middle — <b>3-Down</b> and the <b>central Across</b>. Because a crossing pair shares exactly one cell, everything fills in but that intersection: a single unclued square at dead centre — the <b>keystone</b> (ringed).</p>
    <p>It is recovered from the two crossing words alone. Each shows four of its five letters, so neither is a wild guess and neither is a gimme — the centre is held by their <em>mutual</em> constraint, the smallest possible instance of "the grid carries the solve." A gentler point on the same <code>minvis</code> dial as <a href="endogenous.html">Half the Clues</a> (here <!--MINVIS-->), but a more sculpted one: the logic is a single point at the heart of the grid rather than a six-wave cascade.</p>
    <p>The counter still never names a word — “◇ N still fit” until the pattern is unique, then <b>◆ one word fits — deduce it</b>. Full write-up: <code>docs/relational-difficulty.md</code>.</p>"""

PUZZLES = {
    "endogenous": {
        "out": "endogenous.html",
        "select": "floor",
        "difficulty": "wednesday",
        "copy": {
            "title": "Half the Clues",
            "day": "Endogenous",
            "eyebrow": "<!--SEEDN--> clues given, <!--DERIVEDN--> forced by the grid",
            "dek": "Only <b><!--SEEDN--></b> of the ten entries have a clue. The other <b><!--DERIVEDN--></b> have <b>none</b> — you deduce them from the crossings. When a word has no clue, its own letters are the clue: a new kind of difficulty from the one trivia measures.",  # noqa: E501
            "note": _FLOOR_NOTE,
        },
    },
    "keystone": {
        "out": "keystone.html",
        "select": "keystone",
        "difficulty": "wednesday",
        "copy": {
            "title": "The Keystone",
            "day": "Keystone",
            "eyebrow": "<!--SEEDN--> clues given · the central cross deduced",
            "dek": "Every entry has a clue but the two that cross in the middle — <b>3-Down</b> and the <b>central Across</b>. Solve around them and the whole grid fills but one square: the centre, held only by those two words. Recover the keystone.",  # noqa: E501
            "note": _KEYSTONE_NOTE,
        },
    },
}


def _emit(spec: dict, avoid: frozenset = frozenset()) -> dict:
    data = build_data(spec, avoid=avoid)
    out = SITE_DIR / spec["out"]
    out.write_text(render(data, spec["copy"]), encoding="utf-8")
    given = [f"{e['num']}{e['dir']}" for e in data["across"] + data["down"] if e["role"] == "seed"]
    print(
        f"wrote {out.name}  seed {data['seed']}  {data['floorSize']} given / "
        f"{data['derivedN']} forced  depth {data['floorDepth']}  minvis {data['minvis']}"
    )
    print(f"  given: {given}")
    print(
        "  deduction profile: "
        + ", ".join(f"{w}@{v}" for _, w, v in data["profile"])
        + "".join(
            f"\n    {e['num']}{e['dir']} {e['answer']}  {html.unescape(e['clue'])}"
            for e in data["across"] + data["down"]
            if e["role"] == "seed"
        )
    )
    return data


def main() -> None:
    floor = _emit(PUZZLES["endogenous"])
    avoid = frozenset(e["answer"].lower() for e in floor["across"] + floor["down"])
    _emit(PUZZLES["keystone"], avoid=avoid)


if __name__ == "__main__":
    main()
