# Relational difficulty — a mini's hardness lives in the crossing graph, not the words

A discovery spike (2026-07), prompted by a clean observation: *difficulty is relational.*
Picture the **maximally hard** word — its clue is useless, so from the clue alone the answer
is one of many. Any *less* hard word has a somewhat-useful clue. Now the relation: if a
gettable word **crosses** the hard word, solving it donates a letter, and the hard word gets
easier. So a word's difficulty is not intrinsic — it is *where it sits in the solve, relative
to what its neighbours give it.*

This doc formalises that, measures it on real grids, and connects it to the "clues internal to
the puzzle's logic" idea. It is the **network generalisation** of `app/difficulty.solve_order`
(D22): where `solve_order` replays *one* greedy easiest-first order with a score-based `gimme`
proxy, the model here takes an explicit **clue-power vector** and computes the whole
*forced-solve DAG* — who unlocks whom, in how many waves, and whether it solves at all. The
spike code is `scripts/relational.py` (deterministic) and `scripts/endogenous.py` (the live
probe). Both are experiment tier, not shipped app surface — the finding is the deliverable
(the D19/D31 discipline).

## The model

A puzzle is a set of entries `E` (nodes) and crossings (edges); each crossing shares one cell.
Each entry `e` gets its letters from two sources — its **clue** and the **crossing letters**
donated by already-solved neighbours. Model the clue as a binary per-entry flag:

- **gimme** — the clue alone pins the answer (a precise definition on a word you know); or
- **useless** — the clue narrows to many candidates (the maximally-hard case is the limit).

This is not a loss of generality that matters: the D26 arc established that for a competent
solver *word obscurity is inert* (a known word is a one-shot lookup however rare), so the live
lever is exactly **clue under-determination** — is the clue enough to write the word, or not.
That binary *is* the clue-power axis.

Propagation, then, is a percolation cascade on the crossing graph:

- A cell is **known** once any entry through it is solved (crossing entries share the cell).
- An unsolved entry becomes **solvable this wave** iff it is a gimme, **or** its currently-known
  cells already force it: `n_candidates(answer, known_cells) == 1` — the lexicon (the solver's
  *full* vocabulary, D21/D22) admits exactly one word for the pattern its crossings have pinned.
- Solve every newly-solvable entry at once (one **wave**), donate their cells, repeat.
- If a wave solves nothing and the grid is incomplete, the remainder **deadlocks** — a Natick
  cluster under this clue-power vector (the maximally-hard-word-with-no-useful-neighbours case,
  now a theorem: *no ordering exists*).

The primitive is `Lexicon.n_candidates(answer, known_indices)` — already in the kernel, already
scored against the full solving vocabulary. The model adds only the wave loop over it.

### The lemma, formalised

> **Lemma.** An entry `e` with a useless clue is solvable iff its crossing neighbours donate
> enough cells that `n_candidates(e.answer, donated) == 1`. If a set of mutually-crossing
> entries all have useless clues and none is forced from outside the set, the set deadlocks —
> there is no valid solve order (a Natick cluster).

> **Corollary (the design lever).** Raising one neighbour's clue-power — cluing a crossing word
> more gently — can unlock `e` by donating a letter earlier. So difficulty is tuned by the
> *placement* of clue-power across the graph, not just its total. **Difficulty-curve design is
> an assignment problem over the crossing graph**, not a per-word knob.

## Quantities it buys (computable, no solve data, trivia-independent)

- **depth** — number of waves to solve. `depth 1` == every entry a gimme: a bag of ten
  independent trivia clues, the interlock a formality (the exact D26 "not a constraint puzzle"
  regime an LLM falls into on an all-precise-clue mini). Higher depth == longer forced-inference
  chains == *the grid carries the solve.*
- **information floor** — the *minimum* gimme set that still solves the grid. The dual of the
  lemma: how few clues must be useful, because the crossings carry the rest.
- **difficulty curve** — the max depth reachable with `k` useful clues, swept over `k`. The
  fair, controllable difficulty of *this exact grid*, decoupled from vocabulary.
- **keystones** — entries whose gimme-status is load-bearing (redact this one clue and the grid
  deadlocks). See the finding below — for fully-checked grids this set is *structurally empty*,
  which is itself the point.

## What the measurements say (`scripts/relational.py`, cw list)

Aggregates over 30+ distinct grids per configuration:

    config                     entries   info-floor (min/med/max)   floor/entries   max depth (med/max)
    5x5 fully-checked >=90        10           4 / 5 / 5                  ~0.5            4 / 6
    5x5 fully-checked >=75        10           4 / 5 / 5                  ~0.5            5 / 6
    5x5 blocked, 4 black        ~10           4 / 5 / 5                   0.50           4 / 6
    5x5 blocked, 2 black        ~10           4 / 5 / 5                   0.50           4 / 6

Three findings, each a little surprising:

1. **Half the clues are logically redundant.** A 5×5 mini's information floor is a *median of 5
   of 10* — give the solver 5 well-chosen clues and the crossings force the other 5. Some grids
   need only 4. This is the over-determination of a dense mini made quantitative: every cell is
   doubly-checked, so most answers are recoverable without their clue.

2. **A grid has an intrinsic difficulty *ceiling*, and it varies.** The best grids cascade to
   depth 6; others top out at depth 2–3 no matter how you withhold clues. Example: the model
   flags `SIP/ARENA/HOLDS/OBEYS/YES/…` (the very grid D26 watched Opus solve as ten trivia
   lookups) as **max depth 3** — structurally shallow — while `HEW/MIXIN/ETUDE/LURED/…` reaches
   **depth 6**. *Cascade-ability is a property of the fill*, computable before a single clue is
   written. This is a new grid-selection signal, orthogonal to word-score.

3. **The hardest fair puzzle is not the emptiest one.** The difficulty curve is non-monotonic
   near the floor: withholding *one more* clue past the peak can *lower* achievable depth (you
   are forced to keep the short-chain ice-breakers to stay solvable). There is an optimal
   withholding, typically at `floor+1`, not at the floor.

4. **Fully-checked grids have no single-clue keystones — structurally.** Redacting any one clue
   never deadlocks a fully-checked grid, because every cell is shared, so if the other nine are
   known the tenth is fully pinned. The Natick therefore *cannot* live at a single clue in a
   dense mini; it lives at the **cluster** level (crossing below the floor) or the **vocabulary**
   level (an obscure word the solver cannot recover — the D26 cliff, orthogonal to this model).
   This sharpens D21's Natick story: in a fully-checked mini, unfairness is never one bad clue.

## Endogenous clues — "clues internal to the puzzle's logic"

The redaction the model uses is the purest **endogenous** clue: a blank clue says *recover this
answer from the puzzle's own logic (the crossings), not from outside knowledge.* Finding 1 says
a mini can carry ~half its answers this way and still be solvable. That opens a design axis the
project has not used: clues that point **inward**, so difficulty becomes inference depth (a
controllable, fair, trivia-independent quantity) rather than breadth of trivia recall.

A rough taxonomy, easy → radical:

- **Under-determined definitional** (the D26 "oblique" regime): the clue narrows to a set; the
  crossings disambiguate. Already the discovered fair-difficulty axis.
- **Redacted / self-checking**: no clue at all; the answer is forced by its crossings. The limit
  case, and exactly what the information floor licenses.
- **Cross-referential**: "Anagram of 4-Across", "3-Down backwards", "Shares a stem with 1-Across".
  The clue's information is *another entry* — pure internal reference.
- **Structural / constraint**: the clue is a rule, not a definition ("no repeated letter";
  "the shaded cells, read down, spell a 6-Down synonym"). The puzzle becomes a constraint system
  a solver *propagates*, like Sudoku — difficulty = the longest forced chain, i.e. the model's
  `depth`, made exact and solver-independent.

The strategic payoff: with endogenous clues, `depth` is not a *proxy* for difficulty — it *is*
difficulty, identical for every solver, and dialled precisely by the clue-power assignment. That
is the closest this project has to a knob for "perfect the difficulty curve of a mini."

## A third difficulty axis — retrievability from a pattern (playtest finding)

Playing the redacted mini surfaced a difficulty the model was silent on. In the first build the
first deducible entry was **MACYS** (`··CYS`). It is *lexically* forced — exactly one word in the
vocabulary fits — yet a human does not *generate* it from the pattern: it is a proper noun, and
you can't enumerate the survivor in your head even though you'd recognise it instantly if shown.
**Forcing (candidates == 1) is not the same as retrievability.**

This closes a loop back to the project's origin. Difficulty was first framed as **word obscurity**
(D5/D9); the D21–D26 arc then showed obscurity is a *fairness cliff, not a slope* (a known word is
inert however rare; an unknown one is a Natick), and that **clue obliqueness** is the dominant
*fair, graded* axis — *when clues exist*. Strip the clue, as the endogenous puzzle does, and word
difficulty returns, but as a **third, distinct thing**:

| axis | question | shape | where |
|------|----------|-------|-------|
| word obscurity (D9) | do you *know* the word? | cliff (known / Natick) | any puzzle |
| clue obliqueness (D26) | how vague is the *definition*? | graded, fair | when clued |
| **retrievability** (this) | can you *produce* the word from its **letters**? | graded, fair | the no-clue regime |

The reframe that unifies them: **when the clue is gone, the crossing letters *are* the clue.** So
retrievability is clue under-determination (D26's fair axis) with the "clue" being a letter-pattern.
But the two notions of "precise" now **come apart**: a pattern is *lexically* precise when few words
fit it (the model's `n_candidates`), and *humanly* precise when a person can produce the survivor
(frequency, dictionary-membership, pattern-typicality). For a definitional clue these roughly align;
for a **letter-pattern clue they diverge** — `··CYS` is lexically maximal (1 fit) but humanly
minimal. That divergence *is* the axis, and MACYS is its signature.

Two computable quantities govern it, both trivia-independent:

- **`minvis` — the visibility profile.** For each forced entry, how many of its letters are already
  showing at the moment it becomes unique. The demo grid's original profile was `3,3,4,4,5`: the
  cascade was *hardest first* (MACYS forced at 3 of 5) and trivial last (a fully-spelled word you
  just read off). `minvis` = the minimum over the cascade is the deduction-difficulty knob: **5** =
  read it off · **4** = a gentle one-blank recall · **3** = a real two-blank deduction.
- **retrievability of the forced word** — a dictionary + frequency filter (proper nouns / slang /
  obscure words *out*), so the survivor is always a word a person can produce.

**A small theorem, and the tension it names.** A *genuine* cascade *requires* forcing some words
with blanks still showing (else it is the degenerate "all one direction" floor with no deduction at
all). But a pattern is forced precisely when *few* words fit it, and sparse-but-forcing patterns
select for *rare* letter-combinations — which tend to have *rare* survivors. So "the grid carries
the solve" structurally routes you toward the least-common words first. You cannot have both a real
deduction chain *and* every deduced word be a fully-spelled common word — they pull against each
other. The fix is not to eliminate the tension but to *bound* it: keep every answer a common
dictionary word (retrievability) and hold `minvis` at the target (e.g. 3 for a fair "real
deduction", 4 for a gentle one).

This is now a **generation constraint**, not just an analysis: `site/build_endogenous.py` selects
the demo grid by exactly this filter — first top-tier fill whose ten entries are all common
dictionary words and whose cascade's hardest forcing still shows `minvis` letters. The playable
result (`seed 60`: `APPLE/RELAX/ERASE/NICER/ALERT` × `ARENA/PERIL/PLACE/LASER/EXERT`) is a
4-given / 6-forced, depth-6 mini whose openings (`·R·NA`→ARENA, `·X·RT`→EXERT) are real two-blank
deductions of household words — and, unlike the first build, the first wave offers *two* deducible
entries, not a single funnel. `minvis` is a genuine Mon↔Sat dial for the deduction phase, the
complete/deterministic analogue on the *solve-from-the-grid* side of the soft clue-obliqueness axis.

### Composing where the deduction lives — the clueless set as a design surface

Once the no-clue solve is *explicit*, **which** entries you leave clueless is a compositional
choice, not just "the minimum floor." Two refinements fall out, both live in the playable set:

- **Retrievability is required only where the clue is withheld.** In the floor puzzle every entry
  is deduced by *someone*, so every entry must be a common word. But if you *designate* a small
  clueless set, only *those* answers must be retrievable — the clued entries can be any word a clue
  can name. This is the general selection rule (`build_endogenous.py`'s `keystone` spec checks
  commonness only on the clueless pair), and it vastly widens the usable grids.
- **A crossing clueless pair leaves exactly one unclued cell — their intersection.** Blank two
  entries that cross and clue everything else, and every square is given but the one they share.
  Put that at the grid's centre and you get **the keystone** (`keystone.html`): 3-Down and the
  central Across left blank, meeting at dead centre; the eight perimeter clues fill everything but
  the middle square, which is recovered from the two crossing words alone (each shows 4 of 5
  letters, so `minvis` 4 — neither a gimme nor a guess). It is the *smallest* instance of "the grid
  carries the solve" — a single point of deduction, sculpted rather than cascaded. The floor
  puzzle and the keystone are the same engine and the same fairness rule at two ends of a
  **composition** axis: *how many* clues you withhold (the floor) is one knob; *where* you withhold
  them (the shape of the clueless set) is the other, and it carries the aesthetics.

The flagship presentation is `site/latent.html` (`build_flagship.py`): a 4-given / 6-deduced,
depth-6 mini that draws the forced solve as a **forcing graph** propagating through the grid, and
ends in a **solve debrief** surfacing the otherwise-invisible structure — the floor, the cascade
depth, the *ice-breaker* (the first clueless entry cracked, and with how few letters showing), and
an estimated deduction difficulty from `minvis` + depth. It is the whole model turned into a single
playable experience: the latent logic puzzle every crossword hides, made the point.

An earlier build drew this as a single **thread** — a polyline through the clueless entries' centroids
in solve order. It looked alive but misrepresented the structure: consecutive entries in the order
often do not cross (the cascade is a *wave-DAG*, not a chain), so a segment between two centroids
encoded nothing, and the reader's instinct to read the line *spatially* had nothing to land on. The
forcing graph fixes this by anchoring every edge on a **real donor cell** — a cell of the blank entry
whose crossing neighbour is solved in an *earlier* wave, i.e. a letter already known when the entry
becomes unique (exactly the `minvis` set). Each blank's edges light when it falls; the clue list
carries the **wave number** (the order, shown explicitly rather than inferred from a path); and
selecting a blank rings precisely the letters that pin it. The geometry is now load-bearing: an edge
*is* a forcing relationship, touching the letter that carries it. All of this is derived client-side
from the entries' `wave`/`cells`/`role` — the baked puzzle data is unchanged.

### Scaling Latent — low density and a long word (`build_latent_long.py`)

`site/latent-long.html` probes the far end of the space from the dense 5×5: a **low-density 9×9**
(~55% white) built around a single 9-letter across **spine**, `ESTRANGED`, that is *deduced*
(8 given / 10 deduced, depth 5). Building it surfaced three load-bearing facts:

- **Full-checking forbids sparse grids.** The blocked engine rejects "orphans" (a white cell in a
  run below `min_len`), so every white cell is crossed both ways — you cannot build the thin,
  unchecked-cell grids real crosswords use. "Low density" here is a *larger grid with more black*,
  not a thinner lattice. A lone long word is impossible for the same reason: a fully-checked
  9-across drags a 3×9 word-square band. The escape is a **staggered spine** — crossers stepping up
  on one side of the row and down the other — keeping it a single 9 while every cell stays checked.
- **A long word is a keystone, not a climax.** A fully-checked long entry crosses all of its cells'
  downs, so it accumulates letters fastest and is among the *easiest* to force — left alone it falls
  in the first deduction wave. The information floor counteracts this: by withholding the right
  crossers it places the spine mid-cascade (here wave 3, pinned with 6 of 9 letters — a real
  deduction, not a collapse). But the natural pull is "crack the long word early, it unlocks the
  rest," not "deduce it last."
- **Depth comes from density.** A single hub short-circuits a small grid into a shallow cascade (a
  7×7 spike bottomed out at depth 3). The larger 9×9 recovers depth 5–6 — the interlocking
  constraints that make long inference chains are a *density* effect, so airier grids trade depth
  for openness and you buy it back with size. Practically you get two of {low density, long word,
  clean common fill} comfortably; all three is tight (short crossers skew crosswordese).

Two engineering notes for anyone extending this: exhaustive `information_floor` explodes on
weak-forcing low-density grids (large floors → huge combination sweeps) — greedy is the search tool,
exhaustive only for the final ≤18-entry pick; and layout enumeration (`gen_capped`) is unusable at
9×9, so the layout is a **hand-built template** filled by the real `fill.solve` + relational pipeline.
The page reuses the flagship template generalised for black cells / non-square grids / parameterised
copy; the fill is a reproducible seed search, the clues authored by hand (not the live pipeline).

**One spine or two? (`build_latent_two.py`, `site/latent-two.html`).** A second 9-across spine
(two parallel spines, rows 2 and 6 of a 9×9) makes the tradeoff sharp. Both spines deduce fine, but
each is a hub that must be *fed*: with two competing for crossers, the greedy floor climbs to
**15/28** (half the grid clued, vs 8/18 for one spine), the cascade flattens to **depth 3** (vs 5),
and the between-spine gap is forced into **eighteen 3-letter crossers** — abbreviation soup. So the
"few clues, deduce many" economy is a *single*-hub phenomenon; a second spine roughly doubles the
long-word payoff (both can be showy/obscure — the over-determination that lets one spine be arbitrary
applies to both) while more than doubling the clue cost. One spine is the sweet spot; two is a
legible demonstration of *why*. (28 entries is well past the exhaustive-floor ceiling, so its floor
is greedy — likely not minimal, which if anything understates the cost.)

**The central-focus cross — topologically ideal, lexically infeasible (measured, not shipped).**
Two *parallel* spines diffuse the puzzle; the natural fix is to make them *cross*, giving a single
**focus**. The clean version is two 5×5 word-squares kissing at one corner cell, threaded by a
9-across and a 9-down that span both (the layout is the intersection of the single-spine stagger
with its own transpose). Topologically it is exactly the attractor you want: the shared cell (4,4)
is a graph **articulation point** — it lies in the two spines and nothing else, so removing it
splits the grid in two — and every crosser is a proper 5-letter slot (no 3-letter soup). But it does
not fill with common words. Two word-squares *coupled* by two 9-letter-word constraints collapse the
common-word solution space to the vocabulary's obscure tail: it fills instantly against the full cw
list (ENTRUSTED / SAPSUCKER spines) but is **unfillable by ~cw-45**, and even ~cw-35 is
AMOOT/RAFIK/DUENA/ENERO soup. So focus and fill-quality trade off directly — the tighter you couple
the deduction to one point, the more the coupling forces obscurity. A *fillable* central focus would
need looser arms (staggered 3-thick crossers instead of full squares — an untried perpendicular
stagger), trading some of the crispness of the articulation point for vocabulary room. Not shipped:
an obscure-word grid is unfair to *deduce* (the point of Latent), so this stays a measured tombstone.

That loosening is the shipped **`site/latent-cross.html`** (`build_latent_cross.py`): two *7*-letter
spines (ESSENCE × OBSERVE) crossing at the centre, arms pinwheeling into two sparse clusters (~35%
white, 14 entries). Shortening the spines and staggering the arms slackens the coupling enough that
the fill draws on **common** words again (the strict cross could not) — the prediction held. The
cost is exactly the crispness we traded: the two spines share the centre letter, so the information
floor must clue *one* of them to force the other (only one spine is deduced, not both), and the
sparsity flattens the cascade to **depth 2** — the shallowest of the family. So the full spectrum,
from densest to airiest, reads: dense 5×5 (depth 6) → one 9-spine (depth 5, the keeper) → two
parallel 9-spines (depth 3, half-clued) → sparse 7×7-spine cross (depth 2, one-deduced). Focus,
depth, and fill-cleanliness form a single tension surface; the one-spine grid sits at its knee.

## The live probe (`scripts/endogenous.py`) — does a real solver track the model?

The probe takes one generated grid, clues it with *precise* (Monday) clues so an un-redacted
clue is a genuine gimme, then runs the live Claude solver (Opus, `--policy none`, no feedback)
under three clue-power regimes and reports thinking-token spend. It closes the analytical ↔
empirical loop the notes leave open.

**Result 1 — below the floor, the live solver fails (the theorem, confirmed).** On the shallow
`SIP/ARENA/HOLDS/…` grid (max depth 3):

    regime                                      pred     solved  turns  think_tok
    all-clues (trivia bag)                      depth 1   True      1       4509
    floor-only (5 clues, 5 endogenous)          depth 2   True      1       1175
    below-floor (4 clues)                       deadlock  False     6       6646

The sharp prediction held: crossing **below the information floor deadlocked the live solver** —
it never solved, burned all six turns, and spent the *most* reasoning flailing. This is notable
against the D26 caution that "redaction doesn't bind, because an LLM recognises the words": at 4
clues the remaining cluster genuinely could not be recovered, and even Opus failed. The
Natick-cluster theorem is reproduced empirically, on the clue-power axis rather than the
vocabulary axis.

Two honest caveats this grid exposes:

- **Thinking-tokens are a noisy, secondary signal** (as D26 already found). Here *floor-only*
  cost *fewer* tokens than *all-clues* — because this grid's minimal floor is the degenerate
  "all five acrosses" set: knowing one whole direction trivially fills every cell (depth 2, no
  real cascade). The clean, robust signal is the **pass/fail at the floor boundary**, not the
  token count.
- To force a genuine cascade you must pick a grid whose *minimal* floor is itself deep, not the
  one-direction set — which the model can select (`information_floor` returns the max-depth
  minimal set). See Result 2.

**Result 2 — a genuine cascade saturates the solver's reasoning (effort tracks depth).** The
`HEW/MIXIN/ETUDE/LURED/PBR/…` grid (seed 0) has a *non-degenerate* depth-6 floor: its 5 gimmes
(HEW, MEL, NED, LURED, PBR) force `MIXIN → ETUDE → HITUP → EXURB → WIDER` over six waves, purely
from crossings — authentic internal-logic solving. Live (Opus, `--policy none`, one turn):

    grid (model depth)          regime               solved   think_tok
    SIP/ARENA/…  (shallow, d3)   floor-only (deg. d2)  True       1175
    HEW/MIXIN/…  (deep,    d6)   all-clues  (d1)        True       6007
    HEW/MIXIN/…  (deep,    d6)   floor-only (real d6)   —      >=20000 (cap)

On the deep grid, blanking the five crossing-forced clues drove the solver to **exhaust its
entire non-streaming reasoning budget (20000 tokens) in a single turn** — ≥3.3× the 6007 the
*same grid* cost with all clues present, and ≥17× the shallow grid's degenerate floor. The model's
structural depth cleanly discriminates a real cascade (saturates reasoning) from a degenerate one
(trivially cheap). *Effort tracks predicted depth.* (Method caveat, consistent with the D26 notes:
the adapter is non-streaming to keep `thinking_tokens`, so 20000 is a hard measurement ceiling —
raising it trips the SDK's "streaming required past 10 min" limit, which loses the count. The
depth-6 solve is therefore *more* reasoning than the harness can capture in one turn; `solved` is
undefined because the move was truncated mid-propagation, the documented 20k-cap artifact, not a
genuine miss.)

Net: the two grids bracket the prediction. **Below the floor → real deadlock/failure** (Result 1).
**At a deep floor → reasoning saturates** while a shallow floor stays cheap (Result 2). The
relational model's `depth`, computed with no solve data, predicts both.

## Where this sits, and what is open

- It **generalises `solve_order`** (D22) from one greedy trajectory to the DAG; it is the
  "distribution over solve paths / real belief-propagation" the D22 open-question named, in a
  restricted (binary clue-power) form. A graded clue-power vector (a clue reduces an entry to a
  candidate *set*, not a binary) is the natural next refinement — it needs a clue→candidate-set
  model, which is a soft, LLM-side quantity (blocked on the same calibration as D21 layer B).
- It gives batch curation (D21 layer C) a **per-grid difficulty ceiling** (max achievable depth)
  and an **information floor**, both cheap and complete — real scheduling signals.
- The **fairness cliff (vocabulary)** stays orthogonal and unmodelled here by design: this model
  holds all words known and varies only clue-power, which is precisely the *fair* axis D26
  isolated. Fusing the two (obscurity × structure) into one calibrated Natick score is still the
  standing open question (needs the score scale settled, invariant 4).
- **Not shipped as app surface.** The pure model would sit beside `app/difficulty.py` if promoted
  (representation-agnostic, takes an `n_candidates` callable — same seam as `analyze`). Promotion
  is a D-entry decision once the live loop shows the depth signal is worth calibrating against.
