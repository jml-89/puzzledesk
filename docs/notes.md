# Running notes

Miscellany that does not fit README or the other docs: benchmark numbers,
environment quirks, data provenance and exact regeneration commands, and gotchas
that cost time. Append freely.

## Benchmark results (as measured this spike)

Machine: the ephemeral dev container (see below). NumPy 2.4.x, single-threaded
Python. Numbers are order-of-magnitude, not tightly controlled.

Packing is easy while the list is large:
- 5x5 on the weak list at Zipf>=2.5 (~4550 words), NON-distinct: ~82 ms/run,
  40/40 solved, median 0 restarts. Interlock does not bite when the list is big.

> The sampler engine was **removed** in D19. The numbers below are kept deliberately:
> they are the measured evidence for that decision — the record of an idea that was
> tried, measured, and retired. `compare.py`/`frontier.py`/`samplers.py`/`quality.py`/
> `bench.py` (the drivers that produced them) are gone with it; recover from git if you
> ever re-open the question.

Sampler vs backtracking, 5x5, weak list, filtered, distinctness OFF (the ORIGINAL
early comparison, before the sampler enforced distinctness), same acceptance bar:
- T(Zipf)=3.0 (3130 words): sampler 2090 ms vs backtrack 33 ms  (64x)
- T=3.5 (1972 words):        sampler 3003 ms vs backtrack 17 ms  (174x)
- T=4.0 (1113 words):        sampler 5808 ms vs backtrack 13 ms  (450x)
Speedup GROWS as the list shrinks: stochastic local search degrades exactly where
systematic search improves. This is the empirical basis for D7.

Sampler vs backtracking on the DISTINCT problem (5x5, weak list, distinct=True,
sampler = penalty strategy, 10 seeds; re-measured this container). Both solve the
same problem now, so the comparison is apples-to-apples:
- T(Zipf)=3.0 (3130 words): sampler ~9.0 s (10/10) vs backtrack 0.12 s (10/10)  (~77x)
- T=3.5 (1972 words):        sampler ~22 s (3/10)  vs backtrack 0.27 s (10/10)
At T=3.5 the sampler's SOLVE RATE collapses (3/10) while backtracking stays 10/10
and complete; a raw ms ratio there is misleading because most sampler runs burn
their whole restart budget without solving. This is D7 confirmed on the distinct
problem: backtracking is the right engine for small/hard/filtered lists.

Sampler strategy study (scripts/samplers.py, 5x5, distinct=True, 10 seeds):
- gate (restart on a degenerate valid grid) vs penalty (duplicate-pair penalty in
  the move). On these lists the two are COMPARABLE: penalty is never worse on
  solve rate (10/10 vs 10/10 at T=3.0; 3/10 vs 2/10 at T=3.5) but adds per-step
  overhead (it rebuilds N*26 column strings when near feasibility). Finding: at
  N=5 distinctness is NOT the sampler's bottleneck -- reaching feasibility is --
  so the guided penalty buys only a marginal robustness edge. penalty is the
  default (guided=True) as the principled "actively enforce" behaviour; gate is
  the honest baseline it is measured against. Neither rivals backtracking.

Distinctness cost (5x5, backtracking, this container): removing the symmetric
basin took ~13 ms -> ~380 ms at Zipf>=3.5 (weak list) and ~19 ms -> ~620 ms at
score>=90 (curated). The easy speed was partly degenerate grids.

Honest ceilings (distinct=True):
- Weak list (Zipf): 5x5 tops out ~Zipf>=3.5 (e.g. mates/irene/linda/asset/needs);
  Zipf>=4.0 is provably UNSAT (exhaustive search, ~1.3 s to prove). Fills are
  name-heavy because dwyl has lowercased proper nouns it cannot distinguish.
- Curated list (crossword 0..100 score): 5x5 packs distinct grids with EVERY word
  >= 90 (top tier). Approx per-bar (25 seeds):
    score>=60 (5372 w): 25/25, 25 distinct, ~104 ms; kneel/nolte/aloha/capes/knelt
    score>=70 (4981 w): 25/25, 25 distinct, ~186 ms; acres/rhino/cigar/elect/delts
    score>=80 (4624 w): 25/25, 24 distinct, ~206 ms; parer/acela/turin/crust/hanes
    score>=90 (2384 w): 25/25, 18 distinct, ~844 ms; sedan/credo/rotor/adept/perth

Reading the "solved X/25": backtracking is complete, so one run settles
existence. The 25 randomised runs measure DIVERSITY (distinct grids) and average
TIMING; for UNSAT the ms is time-to-prove-unsat (full tree). Do not read it as a
success rate.

Black-cell fill (blocked.py/fill.py, this container): a 5x5 with corner or edge
blocks fills from the curated list (bar>=50) in a few ms per seed; raising the bar
on a fixed pattern the length-3 bucket empties between bar 90 (SAT, ~200 ms real
search) and 92 (0 three-letter words -> UNSAT), the blocked echo of "the lexicon
is the ceiling". Tiny 2x3 blocked grid: 66,201 distinct fills brute-forced as
ground truth, solver output a strict subset over 60 seeds. (These demos used slots
<= 5 because that was the data reach at the time; data now covers 2..15 — D36 /
lesson-length-ceiling.md.) The curated list has no 2-letter entry above any real bar
(length-2 slots are UNSAT on it).

## Large capped minis — 10x10+ (D24, scripts/largemini.py)

The reframing that makes a big mini work: **cap the maximum entry length, don't grow
the word lists.** A 10x10 with few blacks has length-10 runs (would be a monster of obscure
long words even now that the 6..15 lists exist — D36); cap every entry at `<= max_len` and
it fills from short-word data alone. (The cap is still the lever for a *short-word* big
grid; D36 makes a *longer* `max_len` a supported option, not the default aesthetic.)

The count-driven `gen_patterns` (D13) cannot cap: it validates whole layouts at the leaf
with a min-length-only test, and its orbit-subset order can't prune a run-length bound.
Measured (this container):
- `gen_patterns(10x10, 20 black)`: first layout in **~2.7 s**, longest entry **10 letters**;
  a post-hoc max cap finds nothing (sparse-black layouts are all giant-run).
- `gen_capped(10x10, max_len=5)`: first layout in **~8 ms**, longest entry **5 letters**.

Cap-driven search + fill from cw 2..max_len (40 layout seeds, 10 fill seeds/bar):
- **10x10, max_len=5:** 40/40 layouts found, median layout search **5.6 ms** (max ~140 ms);
  fill **10/10** at bars 50/60/70/75, **38 entries**, median **~180 ms** (up to ~205 ms at 75).
- **12x12, max_len=5:** 40/40 layouts, median **34 ms** (max ~800 ms); fill **10/10** at every
  bar, **44 entries**, median **~250 ms** (up to ~305 ms at 75).

So a capped big mini is *easily* fillable — the cap keeps every slot in the well-stocked
3–5 buckets, so the lexicon is not the ceiling here (unlike the 5x5 top-tier squeeze). An
example 10x10 at bar>=70: `SUN/IDEA/TALC/PROOF/LIMB/IHOP/POET/OVAL/…`.

Scaling edge: connectivity is checked only at the leaf, so the search backtracks heavily at
13x13+ (white-first ~465 ms at 13x13; a 15x15 does not finish). 10x10 is comfortable;
incremental connectivity/symmetry pruning is the "pruning before 15x15" follow-up.

Completeness is preserved for *existence*: an odd `num_black` on a symmetric 10x10 (no centre
cell) yields an empty generator — a proof, the direct echo of D13's odd-count 5x5 proof. But a
*fill* miss under a pattern/node budget is exhaustion, not a theorem (the capped layout space is
astronomically large), and is worded that way.

### Density control (D25)

The D24 free-count search over-blackened: uniform 50/50 choice order gave **22–52%** black on a
10x10, clustered (touching-neighbour fraction ~0.95) — blobby, unlike a real crossword. Design
space measured (10x10, max_len=5, 20 seeds):

    uniform 50/50 (D24)         black 22–50%, distinct 20/20, cluster 0.95   -- too black
    white-first only (no cap)   black 16–48%, distinct 11/20, cluster ~0.8   -- fat 48% tail
    white-bias + ceiling 20     black 16–20%, distinct 11/20, cluster 0.79   -- 312 ms spike
    white-bias + ceiling 22     black 16–22%, distinct 11/20, cluster 0.79   -- clean, ~5 ms

So the lever is a **black ceiling with a little slack** plus a **white-biased order** (D25):
`max_black` bounds the count (complete over "<= K blacks"; below the 10x10 minimum of 16 it is a
provable empty), and the search tries white-first, black-first only 15% of the time. Default
`max_black = round(0.22 * cells)`. Result at the default on a 10x10 (40 seeds):

    black 16–22%, 20 distinct/40, cluster ~0.85, layout search median ~5 ms; fills 10/10 at
    bars 50–75 (~240–440 ms). Example (bar>=70): MALTA/UNION/STERN/HORSE/EXURB/GLIDE/ATLAS.

The tension is four-way — density × diversity × search cost × grid size. A ceiling *at* the
feasibility minimum backtracks pathologically (the 20-ceiling spike; a 12x12 at a tight cap
hangs), so a **layout `node_budget`** (mirroring `fill.solve`'s) bails a runaway seed and the
per-seed loop moves on — the *generation* path budgets, the *existence-proof* path
(`capped_layout_exists`) does not, so "no layout exists" stays a theorem. 12x12 at the default
22% fraction sits near its own minimum, so yield is low (2/12; node budget bailing) — the
frontier, wanting the D24-scaling layout search. `--max-black K` overrides the default density.

## Gibbs layout field vs the complete search (D27, scripts/gibbs.py)

The black-cell layout as a *soft field* (annealed Gibbs over the binary grid: local run-length
legality + density spring + anti-cluster + no-2x2), head-to-head against `gen_capped`'s complete
search on the axis the spike targeted — **aesthetics** at the sizes that already fill. Both give
legal, symmetric, capped layouts; measured this container (defaults: 60 sweeps, T 1.5→0.06):

    10x10, max_len=5, 30 seeds
    method       black %   cluster   2x2/grid       distinct   median ms
    gen_capped   16-22%    0.85      0.27 (max 2)    15/30            5
    gibbs_field  20-26%    0.67      0.00 (max 0)     9/30          197

- **Spread — win:** clustering 0.67 vs 0.85 (blacks visibly better spread).
- **No 2x2 block — categorical win:** 0.00 vs 0.27/grid (up to 2). `gen_capped` emits the
  American-grid defect ~1 grid in 4; the field forbids it by construction (an explicit energy term).
- **Density — a wash:** 20-26% vs 16-22% (a touch denser/wider — the count spring vs the ceiling).
- **Diversity — loss:** 9/30 vs 15/30 (the anneal converges to fewer minima).
- **Speed — loss:** ~197 ms/layout vs ~5 ms (~40x; still sub-second — fine for a generation tool).
- **Fill — unchanged:** both 6/6 from cw 2..5 at bars 60/70, 38 entries (~350-410 ms).

The measurement also surfaced an **unbid bonus at the 12x12 frontier** (15 seeds):

    method       black %   2x2   distinct   median ms   misses
    gen_capped   22%       0     1/2         644        13/15
    gibbs_field  22-26%    0     8/14        563         1/15

`gen_capped` (default cap, node-budgeted) **collapses** near the feasibility minimum — the D25
phase-transition story: 13/15 seeds bail the node budget, 1 distinct layout. The Gibbs field
**misses 1/15, returns 8/14 distinct**, at comparable time — it keeps producing where the complete
search chokes at the threshold, exactly the phase-transition prediction. So the field is *also* the
more productive engine at the size D25 flagged as the frontier, not just prettier.

**Verdict (D27): KEEP, scoped.** It wins on its target axis (spread, guaranteed no-2x2) and at the
12x12 frontier; it loses on speed and 10x10 diversity, and is **not complete** (a miss is budget
exhaustion, never a proof). So `gen_capped` stays the fast default + the sole existence-proof
engine; the Gibbs field is the aesthetic-controlled (and frontier-productive) alternative
(`generate --gibbs`). Example 10x10 (bar>=70): `SUN/PRO/POISE/ELOPE/SOLAR/EMAIL/CHICK/HOLES/STAT`.

### Basin shape x count -- how the sampler fares (D28, scripts/gibbs.py)

The follow-up study: reshape the basin (grid size, energy weights) and change the count (black
density), and watch the anneal's **reject-reason** (`reject_reason` over the raw `anneal_field`:
`ok`/`short_run`/`over_cap`/`disconnected`). All 25 anneals/cell, sweeps=90, this container.

**The count knob has a floor = the jamming boundary (10x10, max_len=5):**

    frac   ok%   short_run  over_cap  disconn   (~22% is the feasibility floor)
    0.14   12%   3          12        7         below floor: over_cap dominates
    0.18   16%   4           8        9
    0.22   28%   4           2        12        AT the floor: ok peaks, over_cap min
    0.26   16%   6           3        12        above floor: over-crowding -> disconn

`ok` is a tent peaked *at* the cap-forced floor. Ask below it and the field can't answer with a
*sparser legal* grid -- only an *illegal* one (`over_cap` runs it couldn't break). This is D25's
phase transition seen from the soft side: the same wall the complete search hits as `node_budget`,
now the sampler's reject profile. 12x12's floor is higher (~26%): `ok` is **0%** at frac
0.14/0.18/0.22 and only reaches 8% at 0.26 -- below the floor the field simply cannot make a legal
grid, exactly as `gen_capped`'s `max_black` below the minimum is a provable empty.

**The failure mode shifts with basin shape (fixed frac=0.20):**

    shape   ok  short_run  over_cap  disconn   target/floor
    10x10   6   4           7        8         20 / ~22
    12x12   4   7          14        0         29 / ~32
    14x14   0   6          18        1         39 / ~43

As the grid grows the fixed frac falls further below the (rising) floor, so failure moves from
balanced -> pure legality. **Connectivity vanishes as a failure mode at size; run-length legality
is what defeats the field as the basin tightens.** The honest reading: the soft field owns the soft
objective, the hard run-length legality is where the complete search still wins -- the soft/hard
split (D15/D21) re-derived inside the layout layer.

**The connectivity repair is defeated by the cap (a negative result):** bridge-whitening fixed
**0/25 disconnected anneals at every density and size**. Under the cap the blacks separating two
white components *are* the cap-load-bearing cells, so whitening a bridge re-creates an over-cap run
(and a 6-run can't split into two >=3 runs). So it was **removed** (D19-style: verdict kept, code in
git); rejection is correct for capped minis.

**The reliable lever is the soft weights (basin reshape works), 10x10:**

    w_cluster   black %    cluster   2x2/grid
    0.0         22-32%     0.90      0.00
    0.55        20-28%     0.73      0.00
    1.2         20-24%     0.71      0.00

Raising the anti-cluster weight moves clustering 0.90->0.71 *and* tightens the density spread, 2x2
staying 0. Where the *hard* constraints jam, the *soft* objective is exactly as controllable as a
field should be -- the reason to have a field here at all.

## Structural difficulty — open crossings (D21, scripts/difficulty.py)

`app.difficulty.analyze` scores each crossing against the *full* solving vocabulary
(cw 5-letter list, 20,292 words) — a cell is *open* if neither crossing word alone
pins the shared letter. Measured on 5 distinct 5x5 minis per bar (this container):

- cw score>=90 (gen list 2384): **~12 open crossings/grid** (9–15), **0 unfair**,
  max ambiguity 4–6. Dense minis are structurally under-constrained (a 5x5
  fully-checked grid has 25 crossings and most cells admit several letters from one
  side), but at the top tier every entry is a common word, so open ≠ hard.
- cw score>=70 (gen list 4981): ~10 open/grid, 0 unfair.
- cw band [50,58] (gen list 924, obscure crossword-ese): **9 open/grid, all 9
  unfair** — with the cutoff at <60 ("below solid") both entries at every open
  crossing are obscure, so each open cell is a genuine Natick (e.g.
  `casas/useme/towit/inigo/tenon` — `towit x sewin` open 6/6).

The finding: **open-crossing count is roughly bar-independent (~9–15)** — it is a
property of the dense 5x5 geometry, not the word quality — while **unfairness =
openness × obscurity**, and the score band (layer A) is the knob that controls the
obscurity term. So the checkability metric (layer A′) and the band (layer A) are
complementary: the band decides how obscure the fill is, the metric shows which
crossings that obscurity turns into Naticks. Openness is scored against the whole
vocabulary and at maximal support (the rest of each word known), so an open crossing
is unavoidably hard regardless of solve order — a conservative signal (D21).

**What openness is really driven by: word length, not crossing count.** The intuition
"a mini is hard because it is densely crossed" is only half right. Split "density" into
(i) *coverage* — are all cells crossed? — and (ii) *support per crossing* — how much
does a crossing pin the shared letter? A cell is open iff *neither* word forces it, and
a word forces it only when its *stem* (the length-(L−1) remainder) is constraining. So
support scales with word length, and the open *rate* falls sharply with size even
though every grid below is maximally dense (all cells crossed), cw>=60, 5 grids each:

    3x3: 9 crossings, open  9/9  (100%), max ambiguity 8–18
    4x4: 16 crossings, open 6–15 (~65%), max ambiguity 7–14
    5x5: 25 crossings, open 8–10 (~38%), max ambiguity 3–6

A 3-letter entry blanked at an edge leaves a 2-letter affix (`_at` → bat/cat/eat/…, ~18
completions), so a 3x3 is *maximally dense yet 100% open* — the crossings barely
disambiguate and it is nearly pure vocabulary recall. A 5-letter stem (`_ATER`) has few
completions, so ambiguity collapses to 3–6. Counter-intuitive upshot: **bigger
fully-checked minis are fairer per cell** — longer words check each other better;
density (coverage) is necessary but not sufficient.

**Black cells = local short-slot pockets.** `scripts/difficulty.py blocked R C K …`
runs the same metric on `patterns.fill_by_count` grids (projected via
`filled_from_blocked`). Bucketing every crossing by its *shorter* (weak-side) entry
length reproduces the size curve *within one grid* (5x5, cw>=60, 5 grids):

    shorter len 3: ~78% open      shorter len 4: ~50% open      shorter len 5: ~24% open

i.e. Naticks concentrate at the 3-letter slots black cells create — a local "3x3
regime" inside a bigger grid. The len-3 rate (78%) sits *below* a pure 3x3 (100%)
because a 3-slot's 4-/5-letter crossing neighbours sometimes pin the letter from their
(longer, stronger) side. So the whole size story is one mechanism seen two ways:
shorten the grid, or shorten a slot with a block — either way the weak side's stem is
what sets openness.

## Solve-order difficulty (D22, scripts/difficulty.py)

`solve_order` replays the fill easiest-first (forced → gimme[score>=80] → hard get) and
reports the trajectory as a kind-string plus the bottleneck. Measured on 5x5 cw minis
(this container), it separates *obscure-but-forced* from a real Natick — which the
static openness reading cannot:

- **cw>=90 (all common):** `GGGGFFGFFF` — 5 gimmes ignite, the other 5 cascade to
  forced, **0 hard-gets**. A grid of common words is a Monday *however open* its
  crossings (10–15 open/grid). This is the dynamic mechanism behind "openness ≠ hard
  when words are common".
- **cw>=68 (mixed):** still **0 hard-gets** despite 8–13 open crossings — obscure-ish
  entries are *forced* by the time the solver reaches them. The payoff: static "open"
  over-counts difficulty; the cascade shows most opens never bite.
- **cw band [50,58] (all obscure):** `HHHHHHHHHF` — no gimmes, so one cold ice-breaker
  (step0, ~20,292 fits = the bottleneck) then support cascades (fits fall
  20292→482→…→4) but every entry stays *hard*: a genuine Saturday, 9 hard-gets/grid.

The ignition knob: on the same [50,58] grids, lowering `gimme` 80→55 (assume the solver
*knows* those words) drops hard-gets 9→7 and the bottleneck from ~20,292 fits to ~140 —
anchoring quantified. Two modelling choices matter (D22): the hard-get order is
support-first (`(-fits, score)`) so the cascade flows through crossings (score-first
picked multiple cold ice-breakers, understating it); and a fully-checked grid has no
forced entry cold, so *ignition requires the gimme signal* — a logic-only solver can't
even start, which is itself the finding. `gimme` is uncalibrated (D21 layer B): vary it
to bracket solver skill, not to claim a Monday/Saturday label.

## Generate-to-a-difficulty (D23, cli.mini --hard)

`mini 5 60 3 --max 90 --hard 6 --gimme 88` — draw fills from the `[60,90]` band, keep
only grids the solve-order model says need ≥6 hard gets under Saturday cluing, return
hardest-first. Deterministic (seeds 0..); this container yields, in order:

    SLOAN/CORGI/USAIN/BELLE/ASSES × SCUBA/LOSES/ORALS/AGILE/NINES  — 7 hard, bottleneck SLOAN
    EARLE/PLAIT/OPRAH/CHINO/HANES × EPOCH/ALPHA/RARIN/LIANE/ETHOS  — 6 hard, bottleneck OPRAH
    DUMPS/USURP/PETAL/LOTTA/ONSET × DUPLO/USEON/MUTTS/PRATE/SPLAT  — 6 hard, bottleneck ONSET

Real, cluable fills (CORGI, USAIN Bolt, SCUBA, OPRAH, ETHOS) — the band floor of 60
keeps them solid, the cap at 90 forces below-gimme crunch. The same decoupling as the
hand-picked `DUETO/DORIC/UHURA…` Saturday (`site/saturday-mini.html`): identical grids
are Saturdays only under high `gimme`; drop `gimme` to 80 and most collapse to a hard-get
or two. The threshold is best-of-budget, not a proof — asking `--hard 9` returns nothing
(no such grid found in `count*40` seeds), which is exhaustion, not UNSAT (D23).

Reproducibility note: `mini 5 70 1` is unchanged by the band work
(`rotor/atone/strep/petal/srsly`, weakest `oneal` 70); `mini 5 70 1 --max 80` bands
to `[70,80]` (2567 eligible) and yields `packs/omani/risen/estee/sheds`.

## Agent solve loop (D26, cli.solve) — live check + first finding

The solving spike was exercised **live** end to end (`uv run --extra clue solve`), against
`api.anthropic.com` with the `ANTHROPIC_API_KEY_TWO` key the container carries. Both stages
work: clue generation, then a Claude agent (`claude-opus-4-8`) solving through the feedback
loop. Two API-shape facts learned live (both now encoded in `adapters/claude_solver.py`):

- Structured outputs (`output_config={"format":{"type":"json_schema","schema":…}}`) work for
  the *clue* adapter (it keeps them).
- Thinking APIs differ by **model family**: Opus 4.8 uses **adaptive**
  (`thinking={"type":"adaptive"}` + `output_config.effort`); Haiku 4.5 uses the older
  **enabled** (`thinking={"type":"enabled","budget_tokens":N}`). Each **400s** on the other
  (`Config.solve_thinking` = `adaptive`/`enabled`/`off` selects it).
- **Reasoning volume is the measurement, so the solver runs *free-form* (no forced schema).**
  Forcing a JSON schema *suppresses the thinking pass and zeros `thinking_tokens`* — the very
  signal we want. Free-form, the model reasons in prose (readable) and ends with a JSON object
  parsed leniently; `usage.output_tokens_details.thinking_tokens` is the effort scalar (the
  thinking *block* itself comes back redacted/empty). Trivial prompt → **0** thinking tokens;
  a mini → **thousands**, so the signal is real and difficulty-responsive.

First finding: **a 5x5 mini is a one-shot for Opus 4.8, even under `--policy none` (no
feedback).** The completion bit saturates (always solved in 1 turn), so the graded tell is
**reasoning-token spend**, not turns.

Clue-difficulty sweep (`scripts/solve_effort.py`, Opus, `--policy none`, thinking tokens; the
fill is identical per seed across difficulties, only the clues differ):

    difficulty  seed0  seed1  seed2
    monday       6585   1697   1028
    saturday     1735   1421   1394

Read: **clue difficulty barely moves reasoning**, and on seed 0's *identical grid* Monday cost
*more* than Saturday. Single-run variance is large (6585 vs 1028), so counts need averaging.

**What the transcripts reveal (the important finding).** Head-to-head on one puzzle (seed 1,
Wednesday clues), Opus vs Haiku, both solved in one turn:
- Both solve the mini as **ten independent trivia clues**, not as a constraint puzzle. Every
  entry (SIP, SELES, INDY, PASS, ARENA, HOLDS, OBEYS, YES, AHOY, ROBE) is gettable from its
  clue alone; the interlock is a *formality they confirm*, not the *means*. Opus even says it —
  "ARENA (crosses give _ _ E N A)" — using crossings only to check. This is why clue difficulty
  does not bite: if the model already knows the word, the crossings never become load-bearing.
- **More tokens ≠ more/better reasoning.** Haiku spent **5737** tokens vs Opus's **1512** (3.8×)
  for the *same* answers — but its extra reasoning is verbose and **partly confabulated**: it
  "verified crossings" with hand-wave ✓s and drew a grid (`IPEAO/NALHB/…`) that does **not**
  match its own (correct) placements. It got the answer because the clues were individually
  easy, not because its interlock reasoning was sound. Since the real thinking block is
  redacted, the prose is a *separate, post-hoc articulation* and can diverge from what happened
  — trust the token **count** as effort, treat the prose as a lossy narrative.
- **Reframing.** Our analytical difficulty (`analyze`/`solve_order`) lives entirely in the grid
  *structure* (open crossings, Naticks). On a mini of common words the models **bypass that
  structure**, so thinking-tokens measure trivia recall + verbosity, not structural difficulty,
  and will not correlate with the model until the puzzle *forces* crossing inference. The
  discriminating lever is therefore **word obscurity** (make the clues insufficient so the grid
  must carry the solve) — the two-sided band the mini path has (`--max`) but the puzzle/blocked
  fill does not expose yet — more than clue wording or model choice.

(The Haiku *table* sweep over 6 puzzles timed out at 590 s — Haiku is slow/verbose; the
head-to-head above is the cleaner read anyway.)

**The lever, found: clue *ambiguity*, not word obscurity.** Threaded a two-sided score band
`[min, max]` through the puzzle/blocked fill (`PuzzleService.generate(max_score=…)`,
`--max-score`) to draw *obscure* fills, and re-ran the head-to-head. Three conditions, Opus,
`--policy none`, thinking tokens:

    condition                                              opus    haiku
    common words (cw>=75), precise wednesday clues         1512     5737
    obscure band [60,75], precise wednesday clues          1368     2915
    obscure band [60,75], OBLIQUE saturday clues           2548      -

- **Obscure words did *not* raise reasoning** (1368 < 1512) — because the clue writer (also
  Claude) gives *precise definitions even for obscure words*: "Jordan's capital"→AMMAN,
  "Alaskan city on the Bering Sea"→NOME, "Turkish word for forest"→ORMAN. A precise clue makes
  any *known* word a one-shot lookup, however obscure; the crossings still never bind. Word
  obscurity alone is not the difficulty lever.
- **Oblique clues nearly doubled it** (1368→2548) *on the same grid*, and — the real tell —
  **changed the solve method**. With precise clues Opus lists answers; with oblique clues
  ("Certain flair for the dramatic", "Far northern spot on the map", "Turkish forest,
  translated") it does genuine **constraint propagation**: anchor a few down-words, then derive
  the acrosses from the accumulated crossing letters + the vague clue ("1A starts E … = ELAN →
  gives 2D=L, 3D=A, 4D=N"; "6A starts O, O-R-?-A-? = ORMAN"). *This* is the grid carrying the
  solve — the regime our `analyze`/`solve_order` structural model describes.

Conclusion for the probe: the axis that makes reasoning-effort track structural difficulty is
**clue under-determination** (the clue alone must not fix the answer), *not* word obscurity or
the Mon..Sat *label*. The genuine Saturday / Natick regime is the *conjunction* — obscure words
**and** oblique clues, so the answer is reachable only through the crossings.

**Difficulty now drives obliqueness (done).** Follow-up (i) is implemented:
`adapters/claude_clue.py::_DIFFICULTY_GUIDANCE` gives the clue prompt a graded Mon..Sat
obliqueness ladder (Monday = direct definition → Saturday = maximally oblique, "not
determinable from the clue alone"). Validated live on the *same* obscure grid ([60,75] seed 3,
Opus solver, `--policy none`), the **enum alone** (no free-text instruction) now grades both the
clues and the reasoning:

    difficulty  example clue (AMMAN / LORRE / RATE)                       opus think_tok
    Monday      "Capital of Jordan" / "Peter of 'Casablanca'" / "Assess"        1071
    Saturday    "It overlooks a very old citadel" / "Casablanca's twitchy       2767
                heavy" / "It might be prime, or panic"

2.6x the reasoning on an identical grid, purely from the label — the clue axis is now a real
knob (previously the label moved nothing; §"clue-difficulty sweep" above).

## 2D difficulty probe: word obscurity x clue obliqueness (D26)

The composition experiment: sweep the two axes (fill obscurity band x Mon/Sat clue obliqueness),
Opus solver, `--policy none`, measure thinking tokens. **Clean matrix** (n=4 seeds/cell; every run
solved in 1 turn, 0 wrong — so completion/turns saturate and thinking-tokens is the only live signal):

    thinking tokens   Monday                     Saturday
    common  (>=75)    1909 1954 1682 1673 (u1805) 2761 3006 2516 7605 (u3972)
    obscure [60,75]   1115 1584 3466 1942 (u2027) 1647 2256 6386 4057 (u3587)

Read carefully, because it **overturns the min-over-routes guess**:

- **Clue obliqueness is the dominant lever** — Monday->Saturday roughly doubles reasoning
  (~1900 -> ~3800) at *both* word levels. Robust.
- **Word obscurity is nearly inert** — common vs obscure is within noise at each clue level
  (Monday 1805 vs 2027; Saturday 3972 vs 3587 — obscure is even *lower*). There is **no
  obscure x Saturday spike**.
- Why: an LLM solver *knows the whole vocabulary*, so word rarity does not block the recall
  route — obscurity only ever bit *through* the clue's precision, which is the obliqueness axis.
  For a strong LLM the "two axes" the design imagined **collapse to one**: clue under-determination.
  This is IRT's point made concrete — item difficulty `b` is relative to solver ability `theta`;
  word-obscurity's contribution is ~0 when `theta` (vocabulary) is effectively unbounded.
- Variance is grid-specific, not band-specific: the two high cells (7605 common/Sat seed3, 6386
  obscure/Sat seed2) are single hard *layouts*, not a word-difficulty effect.

**MEASUREMENT ARTIFACT CORRECTED (important).** An earlier version of this matrix showed a huge
obscure x Saturday "spike/phase transition" (30k-65k tokens, 4-8 turns, one *failure*). Reading
the captured transcripts showed it was **100% an artifact of `max_tokens=8192`**: that is the
*total* output budget (thinking + answer), and on a hard mini the adaptive-thinking pass alone
consumed it, so the model never emitted its move -> the harness looped on empty placements and
"failed". Raising the budget to 20k (non-streaming, to keep `thinking_tokens`; §fix in
`Config.solve_max_tokens`) made the "8-turn failure" (obscure/Sat seed 3) solve in **one clean
turn**. The reasoning was genuine constraint propagation throughout ("6D=RES -> gives first
letters of 6A/7A/8A as R,E,S"); it was being *truncated mid-thought*, not hitting a wall. Lesson
recorded: with adaptive thinking, the output budget must dwarf the thinking spend, and a
`stop_reason==max_tokens` empty move must be surfaced (now annotated), never looped on silently.

Implications for the composition-of-difficulty framing:
- For a **strong** solver, difficulty is set by clue obliqueness alone; the word axis is dormant.
  To reactivate it, the solver's vocabulary must be genuinely limited -- a **weaker model** (Haiku),
  or a human. The 2x2 only has a live second axis *relative to a bounded-ability solver*. That is
  the next experiment (obscure words the solver does not reliably know), and the honest statement of
  what `solve_order`'s two per-entry inputs (word recognizability, clue precision) mean: recognizability
  is `theta`-relative, precision is not.
- Follow-up still open: correlate per-grid thinking-token spend against `solve_order`'s predicted
  hard-gets (the analytical<->empirical loop), controlling for the grid-specific variance seen here.

### Design principle: obscurity is a fairness cliff, not a difficulty slope

A human observation crystallised this: in real minis you never meet a word you *don't know* — the
answers are always in your vocabulary; the difficulty is recall + misdirection on a *known* word.
That is the crossword setter's cardinal rule, and its violation is the **Natick** (D21 A': two
unknown words crossing where neither pins the shared letter). It reframes the two difficulty axes:

- **Word obscurity is a *cliff*, not a slope.** While the word is known, obscurity does nothing
  (Opus: inert across the whole band). The instant it is *unknown*, the puzzle is not "harder" --
  it is *unfair*; effective difficulty jumps discontinuously. There is no graded middle, so a fair
  puzzle never approaches the edge. This is why the obscurity band produced no graded signal.
- **The `min_score` floor is a *fairness* boundary, not a difficulty dial** -- it keeps answers
  inside the assumed solver vocabulary (IRT theta). The two-sided obscurity *band* (D21 layer A) is
  therefore not a fair-difficulty tool; it is a way to deliberately step *past* the floor and
  manufacture Naticks -- useful for *studying* the unfair regime, wrong for "make a good mini
  harder".
- **The only fair difficulty axis is clue obliqueness** (D21 layer B) -- tricky clues on known
  words. The Opus 2D probe found exactly this (obliqueness dominant, obscurity inert), so the human
  design rule and the LLM measurement agree.

Why the Haiku arm is a poor proxy for "limited-vocabulary human": a human is *reliable within* their
word list and hits a clean wall *outside* it (a sharp theta-boundary). A weak LLM is *erratic
everywhere* -- Haiku fails common/Monday seed 0 (the easiest cell) while acing seeds 1-3 -- so it has
noise, not a crisp boundary. Modelling "limited-but-reliable vocabulary" wants a solver whose *word
list* is restricted, not whose reasoning is weakened -- i.e. the fairness floor applied to the
solver, not the setter. Consequence for the difficulty model: layer A should be read as the
*fairness floor + Natick-avoidance constraint*, and graded difficulty should be sought in layer B
(clue) with the fill held above the floor.

### Haiku 2D matrix -- the completion signal un-saturates, along the CLUE axis

Same 2x2 with the weaker solver (Haiku 4.5, enabled thinking budget 10k, opus-written clues),
`--policy none`, solved/4 per cell:

    solved/4     Monday   Saturday
    common       3/4      1/4      <- most failures
    obscure      4/4      3/4

- **Failures track obliqueness, not obscurity.** Saturday = 4/8 fails; Monday = 1/8. And
  **obscure/Monday is a clean 4/4 sweep** -- the weaker solver had *zero* trouble with the "obscure"
  band under precise clues. The word axis stayed dormant *even for Haiku*, because [60,75] is still
  *famous* crossword vocabulary (AMMAN/LORRE/NOME/ENOS) it knows -- the cliff is beyond our band for
  both models. Third independent confirmation (Opus tokens, Haiku failures, human experience) that
  obscurity within the known-word regime is not a difficulty axis.
- **The failures are genuine, verified by transcript** (not another artifact): on a failed
  common/Saturday grid Haiku places a *complete but wrong* fill each turn and, with no feedback,
  second-guesses itself into *different* wrong fills (6A cycled DRYAD->DRUID->NOMAD->REBEL) without
  converging -- a real solver defeated by oblique clues, not an empty-move stop. (Only the final turn
  truncated; the failure predates it.)
- Caveat on the Haiku numbers: enabled-mode thinking (fixed 10k budget) plus Haiku's verbosity
  occasionally overflows the 16k non-streaming cap on a late turn (annotated). It hampers the tail,
  not the qualitative verdict. A cleaner weak-solver probe would *restrict the solver's word list*
  (the real analogue of a bounded-vocabulary human) rather than lean on model weakness, which is
  erratic rather than cleanly bounded.

### Vocabulary floor: the word axis is live only through STRUCTURE (a Natick), and only vs true unknowns

The faithful bounded-vocabulary solver (an LLM cannot "forget", so): pick a floor `theta` = the
solver's known-word boundary, and **redact the clue** for any entry scoring below it -- the solver
is told it does not know that word and must recover it from crossing letters alone (a human meeting
a word outside their vocabulary). Two probe grids (Opus, `--policy none`, floor 75, fill band
[62,90]), each classifying every below-floor entry as *forced* (all cells shared with a KNOWN
perpendicular) or *Natick* (a cell shared only with another unknown):

- **Seed 0 -- genuinely obscure fill (XACTO 65, ONICE 65, COPAY 70; a 3-way cluster).** `solved=False`.
  The solver failed at **exactly the predicted Natick cell**: XACTO->XASTO and ONICE->ONISE, both
  wrong at the *same* shared cell (2,3) where the two un-recognized words cross (it guessed S; answer
  C). Where a crossing word *was* recoverable (COPAY, which it got), the cell resolved. This is the
  analytical Natick (`analyze`) reproduced *empirically* -- the loop closed.
- **Seed 1 -- famous names below the floor (MAE 65, ELON 65).** `solved=True`, one turn. It got
  MAE and ELON right *despite* redacted clues, because it **recognizes famous names from a partial
  pattern** regardless of crossword score.

Conclusions:
1. **Word difficulty is real but purely *structural*.** Obscurity never grades a single entry (a
   redacted word with a KNOWN crossing is still forced); it only bites at an **unknown x unknown
   crossing** -- a Natick. So the word axis lives exactly where `analyze`/`solve_order` said it does,
   and nowhere else. "Harder words" is not a difficulty dial; "unknown words crossing each other" is
   a fairness cliff. Same lesson as before, now demonstrated end-to-end with a real solver.
2. **The effective vocabulary boundary is *recognizability*, not crossword score.** The score floor
   mislabels famous-but-low-score entries (MAE, ELON) as unknown; the LLM knows them anyway, so the
   redaction does not bind. The empirical Natick occurs precisely where two *un-recognizable* words
   cross (XACTO x ONICE), which is the LLM's true `theta`, not the score threshold. For a *human*
   with a genuinely bounded list this mechanism is faithful (redact the words they truly do not know);
   for an LLM few words qualify, and the honest bounded-solver is the analytical `solve_order` run
   against a vocabulary-floored lexicon.

Net of the whole D26 arc: **difficulty = clue obliqueness on known words (the fair, graded axis);
word difficulty is a structural cliff (unknown x unknown = Natick), not a slope.** Confirmed by Opus
reasoning-tokens, Haiku failures, the vocabulary-floor Natick reproduction, and a human's lifetime of
minis. The empirical agent and the analytical `analyze`/`solve_order` model agree.

## Solution-space size (D31 — spike tombstoned)

> The `backtrack.count` counter and `scripts/count.py` that produced these numbers were
> **removed** (D31 tombstone; code one `git show` away). The numbers are kept deliberately,
> D19-style — they are the measured record of the spike. Canonical write-up:
> `docs/postmortem-kernel-methods.md`.

`backtrack.count` exhausted the complete search to count *how many* distinct minis a
bar admits (not just whether one exists), returning `(n, exact, nodes)`: `exact`
True == the tree was walked to the end, so `n` is the exact total (a theorem, the
counting twin of a `None` UNSAT proof); a `limit` hit reported `exact=False` (`>= n`).
Measured this container:

**The space collapses to a countable set as the bar rises**, weak (Zipf) list, N=5:

    T=3.5 (1972 w): exactly  56 distinct minis |   572,703 nodes | ~26.5 s
    T=3.7 (1601 w): exactly   8 distinct minis |   197,297 nodes |  ~7.8 s
    T=3.9 (1257 w): UNSAT (exactly 0)          |    60,479 nodes |  ~2.1 s
    T=4.0 (1113 w): UNSAT (exactly 0)          |    39,126 nodes |  ~1.2 s

This *refines* the earlier ceiling read ("5x5 tops out ~Zipf>=3.5; 4.0 provably
UNSAT"): the exhaustive count puts the true edge **between 3.7 and 3.9** (3.9 is
already UNSAT), and shows the last SAT rungs are a mere 8 then 56 grids.

Curated (cw 0..100) list, N=5:

    T=90 (2384 w): exactly 38 distinct minis   |   702,999 nodes | ~36.8 s

So the curated **top tier (score>=90) admits exactly 38 distinct 5x5 minis** -- the
denominator behind the ceiling note's "25 seeds found 18 distinct" (25 random runs hit
18 of the 38 that exist). Above 90 the list has only 3 words (trivially UNSAT); below
the top tier the space is astronomically large -- exhaustive counting is infeasible
there (single-threaded Python walks ~40k nodes/s), so you cap and report `>=`, or leave
it. Net: every prior "ceiling" now has a *size* beside it, and batch-variety
reasoning (open-questions "Grid variety") finally has a real denominator -- at the very
top the pool you can draw distinct grids from is *tiny* (38), which is exactly why
top-tier fills repeat.

**Early distinctness pruning -- measured and dropped (D31).** A sound prune (a column
prefix admitting one column word forces its down word; reject if it is already
used/duplicated, before the `r==n` leaf) cut only **~2% of nodes** (2.1% weak, 2.6%
curated) and was time-neutral: the forced-down condition rarely fires until deep in the
tree, where the leaf check catches the duplicate anyway. A marginal, time-neutral
optimisation is removed with its number recorded (D19/D28 discipline), not kept as an
off-by-default knob. Code is in git; this is the memory.

## Environment quirks (dev container)

- Fresh container, initially EMPTY repo (zero commits). Because the first pushed
  branch becomes the GitHub default, the working branch `claude/empty-repo-review-
  0vagwh` became default; `main` was added later (D10). The default-branch SETTING
  has since been flipped to `main` (the empty-repo artefact is resolved).
- Nothing preinstalled: no NumPy, no JAX, no system word list. `pip install numpy
  wordfreq` works (installs NumPy 2.4.x, wordfreq). JAX not installed (deferred).
- Container is EPHEMERAL and restarts lose /tmp and background tasks. Anything
  worth keeping must be committed. During this spike a restart killed background
  benchmark jobs; re-run rather than resume.
- Do not chain `sleep` in one bash call to wait; the harness blocks it. Use
  background runs or an until-loop.

## Data provenance and regeneration

Two families, DIFFERENT SCORE SCALES (architecture.md invariant 4). All three lists now
ship **lengths 2..15** (D36); the ad-hoc awk recipes below were replaced by reproducible
`scripts/*.py` drivers (each `--min-len/--max-len`, default 2..15, default canonical URL
or a local `--source`).

Weak baseline — `data/words_N.txt` and `data/scored_N.txt`:
- Source: dwyl english-words `words_alpha.txt` (~370k words). Public domain.
  URL: https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt
- GOTCHA (historical, now handled in-script): that file has CRLF line endings, so a naive
  `awk 'length($0)==n'` counts the trailing \r and every length bucket is off by one.
  `gen_words.py` strips/lowercases/alpha-filters, so this no longer bites.
- Regenerate: `uv run scripts/gen_words.py` (plain per-length lists), then
  `uv run --extra scoring scripts/gen_scored.py` (writes `scored_N.txt` as "word zipf"
  for Zipf >= 2.0, dropping zero-signal junk like 'aalii'). dwyl master is a *moving*
  upstream: re-slicing an already-committed length gives the same set but may reorder, so
  only 6..15 were added, 2..5 left as committed.

Curated real list — `data/cw_N.txt`:
- Source: Crossword-Nexus collaborative word list, MIT licensed.
  URL: https://raw.githubusercontent.com/Crossword-Nexus/collaborative-word-list/main/xwordlist.dict
  Format: `WORD;score`, score 0..100, ~567k entries incl. de-spaced phrases and
  proper nouns (uppercase, no spaces). Convention: 60+ solid, 50 acceptable,
  <=30 weak/roll-your-own.
- Regenerate: `uv run scripts/gen_cw.py` (lowercase, alpha-only, score>=25, dedupe keeping
  the highest score, sorted by score desc then word). This re-derives the committed
  `cw_5.txt` **byte-exact** (20,292 words) — the reproduction gate that pins the rules.
- Provenance/licenses also recorded in data/SOURCES.md.
- Only the DERIVED length lists are committed; the raw dumps are not.
- Length reach (D36): the payoff is *less-dense* large grids, not bigger squares (max word
  length and double-square order are separate axes — see D36). A 12x12 capped at `max_len=7`
  (bar 60) fills with real 7-letter entries in ~3.9 s — an open texture the `max_len<=5` cap
  could not reach. A 6x6 double square filling at bar 40 is only a data-reach check; order-7
  squares stay hard (a 7x7 `mini` did not finish in 180 s) — a density/search limit, not data.
- QA finding (D20): for *generating* clean puzzles the practical floor is ~75, not
  the list's "60+ solid" convention. At `min_score 60`, a 5x5 fill admitted `LEDON`
  (a non-word the list rates 60); `min_score 75` produced only real words across
  seeds. So `puzzle` defaults to 75. This is a data property of `cw_N.txt` (the
  border of "solid" is soft, and 60 lets a few junk entries through), not an engine
  bug — the fill faithfully placed a word the list rated acceptable.

## Gotchas that cost time

- CRLF in the dwyl list (above).
- Score scales differ per list; a threshold only means something against its own
  list. `ceiling.py` chooses default thresholds by list name for this reason.
- Empty-repo default-branch behaviour (above).
- Brute-force enumeration is only viable at N=2; at N=3+ on a permissive list the
  count is huge — do not enumerate the full list.

## Architecture refactor (D14) — what changed for a driver author

- The package is now layered (`core < app < adapters < bootstrap < cli`) and the
  gate grew two commands: `uv run lint-imports` (the layers contract) and
  `uv run pytest`. Run all five before pushing (see CONTRIBUTING).
- Engines take `rng=` (a `core.rng.Rng`), not `seed=`. A benchmark driver builds
  the container (`from puzzledesk.bootstrap import build; c = build()`) and calls
  `engine.solve(sq, rng=c.rng_factory.create(seed), …)`; word lists come from
  `c.lexicon.load("cw"/"scored"/"words", n[, min_score=…])` / `load_multi(...)`.
  No more `DATA = Path(...)` or bare `np.random.default_rng` in a script.
- Reproducibility is unchanged: `NumpyRngFactory.create(seed)` is
  `default_rng(seed)`, so a `(lists, seed)` pair reproduces bit-for-bit (the first
  `mini 5 70` grid — `rotor/atone/strep/petal/srsly` — is identical pre/post).
- Kernel lexicon loaders are now pure text parsers (`from_scored_text`,
  `from_words_text`, `from_scored_texts`); the file read moved to the `FileLexicon`
  adapter. If you regenerate lists, nothing about the *files* changed.

## Repo status at end of the *initial* spike (historical snapshot)

A point-in-time record of the first spike's HEAD, kept for the arc. Later spikes
superseded most of the "not started" list (see the decision log / open-questions):
black-cell grids landed at D12–D13/D24–D27, clue generation at D15/D16/D20, and the
`from_scored_file` kernel read was replaced by `from_scored_text` + the `FileLexicon`
adapter at D14. Read the current shape from `docs/architecture.md`, not from here.

- On `origin/main` at the spike HEAD (8 commits). Working tree clean.
- Engine: complete backtracking (the sampler, once secondary, was retired in D19).
  Distinctness enforced in backtrack + validate (+ fill for blocked grids). Curated
  list wired via `from_scored_file` (later moved to the `FileLexicon` adapter, D14).
- Deliverable: `scripts/mini.py` generates distinct minis above a quality bar.
- Not started *at that point*: clue generation, cross-batch variety, JAX, black-cell
  grids (all but cross-batch variety and JAX have since shipped).

## Relational difficulty — the crossing graph as a latent logic puzzle (spike, 2026-07)

Formalised the "difficulty is relational" lemma as *information propagation on the crossing
graph* and measured it (`scripts/relational.py`; full write-up `docs/relational-difficulty.md`;
D38). Each entry's clue is a binary gimme/useless; an entry solves once it is a gimme or its
crossings force it (`Lexicon.n_candidates == 1`); propagation runs in parallel waves to solved
or **deadlock** (a Natick cluster). The network generalisation of `solve_order`'s single greedy
order (D22).

Deterministic measurements, 30+ distinct grids per config (cw list):

    config                     entries   info-floor min/med/max   floor/entries   max depth med/max
    5x5 fully-checked >=90        10          4 / 5 / 5               ~0.5             4 / 6
    5x5 fully-checked >=75        10          4 / 5 / 5               ~0.5             5 / 6
    5x5 blocked, 4 black        ~10          4 / 5 / 5                0.50             4 / 6
    5x5 blocked, 2 black        ~10          4 / 5 / 5                0.50             4 / 6

- **Information floor ≈ half.** A 5x5 mini needs a median of only **5 of 10** clues to be useful;
  the crossings force the other five. A dense mini is ~50% logically redundant — a design budget.
- **Cascade-ability is a per-grid property, computable before cluing** (max achievable depth
  2..6). The D26 "ten-trivia-clues" grid (SIP/ARENA/HOLDS/…) is a shallow depth-3; HEW/MIXIN/…
  reaches depth 6. A new grid-selection signal orthogonal to word-score.
- **No single-clue keystones in fully-checked grids** (structural: every cell shared, so nine
  known clues pin the tenth). Unfairness is a *cluster* or *vocabulary* effect, never one clue.
- **The difficulty curve is non-monotonic** near the floor: the hardest *fair* config is usually
  at floor+1, not the floor (below that you must keep the ice-breaker clues to stay solvable).

Live probe (`scripts/endogenous.py`, Opus, `--policy none`), two grids bracketing the prediction:

- **Below the floor deadlocks the solver.** Shallow SIP grid (model depth 3): all-clues solved
  1 turn / 4509 tok; floor-only (5 real + 5 blank) solved / 1175 tok; **below-floor (4 clues)
  FAILED** (unsolved, 6 turns, 6646 tok). The deadlock theorem, reproduced empirically on the
  clue-power axis — even Opus could not recover the sub-floor cluster. (floor-only was *cheap*
  here only because this grid's minimal floor is the degenerate one-direction set = all five
  acrosses -> every cell known -> depth 2.)
- **A deep floor saturates reasoning (effort tracks depth).** HEW/MIXIN grid (seed 0, a
  non-degenerate depth-6 floor: 5 gimmes force MIXIN->ETUDE->HITUP->EXURB->WIDER over six waves).
  all-clues solved 1 turn / 6007 tok; **floor-only (5 blank clues) exhausted the entire
  20000-token reasoning budget in one turn** (>=3.3x the same grid's all-clues spend, >=17x the
  shallow floor). The model's depth cleanly separates a real cascade (saturates reasoning) from a
  degenerate one (cheap). Method ceiling (as D26): the adapter is non-streaming to keep
  `thinking_tokens`, so 20k is a hard cap — raising it trips the SDK's ">10 min needs streaming"
  limit (which loses the count), so the depth-6 solve is *more* reasoning than the harness captures
  in a turn (its `solved` is undefined — a 20k-cap truncation, not a genuine miss).

**The reframe (dream-big):** a crossword is two puzzles superimposed — a *trivia* puzzle
(clue->answer, breadth of recall) and a *logic* puzzle (crossings->answer, depth of inference).
Today's minis are ~all trivia (depth 1); the crossing graph is a latent logic puzzle we do not
use. `depth` measures how much logic-puzzle a grid *can* carry; **endogenous clues** (redacted,
cross-referential, or constraint clues — internal to the puzzle, not trivia) are how you cash it
in, turning difficulty into a controllable, fair, solver-independent inference depth.
