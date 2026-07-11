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
  minimal set). The `HEW/MIXIN/ETUDE/LURED/PBR/…` grid (seed 0) is such a case: its 5-clue floor
  (HEW, MEL, NED, LURED, PBR) forces `MIXIN → ETUDE → HITUP → EXURB → WIDER` over six waves,
  purely from crossings — authentic internal-logic solving. That deeper live confirmation is the
  next run (a grid where *floor-only* should cost **more** than *all-clues*, not less).

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
