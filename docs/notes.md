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
ground truth, solver output a strict subset over 60 seeds. Data covers lengths
2..5, so demos use slots <= 5; the curated list has no 2-letter entry above any
real bar (length-2 slots are UNSAT on it).

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

## Agent solve loop (D24, cli.solve) — live check + first finding

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
knob (previously the label moved nothing; §"clue-difficulty sweep" above). Remaining follow-up:
(ii) correlate the oblique-clue thinking-token spend against `solve_order`'s predicted hard-gets
to close the analytical↔empirical loop — and, per the composition-of-difficulty framing, split
`solve_order`'s single `gimme` into two per-entry inputs (word recognizability, clue precision).

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

Two families, DIFFERENT SCORE SCALES (architecture.md invariant 4):

Weak baseline — `data/words_N.txt` and `data/scored_N.txt`:
- Source: dwyl english-words `words_alpha.txt` (~370k words). Public domain.
  URL: https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt
- GOTCHA: that file has CRLF line endings. `awk 'length($0)==n'` counts the
  trailing \r, so every length bucket is off by one unless you strip \r first.
  This bit us; strip with `tr -d '\r'` before filtering.
- Regenerate length lists:
    tr -d '\r' < words_alpha.txt > clean.txt
    for n in 2 3 4 5; do awk -v n=$n 'length($0)==n' clean.txt > data/words_$n.txt; done
- Scores: `scripts/gen_scored.py` (needs wordfreq) writes `scored_N.txt` as
  "word zipf" for words with Zipf >= 2.0 (drops zero-signal junk like 'aalii').

Curated real list — `data/cw_N.txt`:
- Source: Crossword-Nexus collaborative word list, MIT licensed.
  URL: https://raw.githubusercontent.com/Crossword-Nexus/collaborative-word-list/main/xwordlist.dict
  Format: `WORD;score`, score 0..100, ~567k entries incl. de-spaced phrases and
  proper nouns (uppercase, no spaces). Convention: 60+ solid, 50 acceptable,
  <=30 weak/roll-your-own.
- Regenerate length-N slice (lowercased, score>=25, sorted by score desc):
    awk -F';' -v n=$n '$1 ~ /^[A-Za-z]+$/ && length($1)==n && $2>=25 {print tolower($1)" "$2}' \
      xwordlist.dict | sort -t' ' -k2,2nr -k1,1 > data/cw_$n.txt
- Provenance/licenses also recorded in data/SOURCES.md.
- Only the DERIVED length lists are committed; the raw dumps are not.
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

## Repo status at end of spike

- On `origin/main` at the spike HEAD (8 commits). Working tree clean.
- Engine: complete backtracking (the sampler, once secondary, was retired in D19).
  Distinctness enforced in backtrack + validate (+ fill for blocked grids). Curated
  list wired via `from_scored_file`.
- Deliverable: `scripts/mini.py` generates distinct minis above a quality bar.
- Not started: clue generation, cross-batch variety, JAX, black-cell grids.
