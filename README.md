# puzzledesk

Dense crossword generation — the NYT-mini style, where a 5×5 grid has no black
cells and every letter is checked twice. That object is a **double word square**
of order 5: five across words and five down words, fully interlocked.

## Approach

Across the two engines here, **state = the N across (row) words**; the down words
are *induced* by reading the grid column-wise. A grid is a valid double word
square iff every induced column is itself a real word.

### The arc (how the design was found)

We started with **energy-based sampling** — the grid as a Markov random field on
a 2-D lattice, `energy = number of invalid columns`, drawn toward zero by an
annealed min-conflicts move (a stochastic `sampler`). It packs 5×5 fast on a big
list. That sampler was the origin of everything below — and, having lost the
head-to-head it set up, was eventually **retired** (see the epilogue and D19). Its
value was the arc, not the shipped code.

Then we built the **acceptance test** as a first-class feedback signal
(`validate.py`), and it corrected the objective. A grid is acceptable iff *every*
across and down word clears a quality bar — a **bottleneck (min) test**, not an
average; one obscure word fails the whole grid. Averaging word-frequency was the
wrong signal.

That reframe collapsed "quality" into **feasibility on a threshold-filtered
list**: filter to words above the bar, solve feasibility, and every result
passes by construction — no soft-weighting. But on the small, hard lists that
high bars produce, min-conflicts wanders. So the right engine became a
**complete propagation-backtracking search** (`backtrack.py`): it solves a
distinct 5×5 in ~0.1–0.3 s where the stochastic sampler needs seconds
(≈50–80× faster), and — on the small, hard lists high bars produce — the
sampler's solve-rate collapses (2–3/10) while backtracking stays 10/10 and,
being *complete*, can even prove when no acceptable grid exists at all.

**Distinctness.** A genuine double word square needs all 2N words distinct.
Otherwise a solver falls into the **symmetric basin** — a grid symmetric down
the diagonal has across ≡ down, the down constraints collapse onto the across
ones, and you get an easy, degenerate fill that's really only N words. Every output
path enforces 10-distinct: the acceptance test, the backtracker (pruning + leaf
check), and — for blocked grids — `fill` (a grid-wide `used` set). Killing the basin
drops backtracking's 5×5 from ~13 ms → ~380 ms (the real problem is harder) and
lowers the honest ceiling.

**Where it landed:** the solver is no longer the bottleneck — the lexicon is. On
dwyl + wordfreq the genuine (10-distinct) 5×5 ceiling is ~`zipf≥3.5`
(`mates/irene/linda/asset/needs`); `zipf≥4.0` is provably UNSAT *for this list*.
That diagnosis was confirmed by swapping in a **curated crossword list** (the
Crossword-Nexus collaborative list, MIT, scored 0–100 for solver-enjoyment): the
ceiling jumps from "UNSAT at zipf 4" to **every word scoring ≥90** — genuine
distinct minis like `sedan/credo/rotor/adept/perth` in ~0.8 s, or ≥70-quality
grids (`rotor/atone/strep/petal/srsly` × `rasps/otter/torts/oneal/reply`) in
~0.2 s. Same solver, unchanged — the words were the whole story.

Building small-first (2×2 → 3×3 → 4×4 → 5×5): at N=2 we enumerate every valid
square by brute force as ground truth; above that, validity is by construction.

**Epilogue — retiring the sampler.** Once the acceptance test turned quality into a
*hard* feasibility problem (no soft objective left to sample against) and complete
backtracking won the head-to-head decisively — ~50–80× faster, and, being complete,
able to *prove* UNSAT where the sampler just burned its restart budget — the sampler
had served its purpose in the arc but earned no place in the shipped system. It was
removed (**D19**): the artifact is deleted, the lesson and the measured numbers are
kept in `docs/decisions.md` and `docs/notes.md`, and `git` holds the code should a
genuinely soft, big-list regime ever reopen the question. Deleting a spike but
recording its verdict is the point — it stops the idea from being silently
re-attempted.

**Black cells (the model generalization).** The induced-column trick above is
load-bearing but only works while every row and column is one full-length word.
Real crosswords have black cells, so a grid becomes a set of **slots** (maximal
white runs, across and down) of *varying length* that **cross** at shared cells —
there is no single column to read. `blocked.py` parses a black-cell pattern into
that slot/crossing graph; `fill.py` fills it as a CSP over slots with the same
complete backtracking (now with MRV ordering and per-slot *pattern* queries into
a length-bucketed `MultiLexicon`), still distinct, still every entry ≥ the bar by
construction. Same small-first discipline: a tiny blocked grid is enumerated as
ground truth.

The block pattern itself is now a **parameter, not a fixed template**: you give a
shape and a *number* of black cells and `patterns.py` searches the legal layouts
— fully checked (no unchecked cells, no sub-`min_len` runs), white cells connected
— with the same complete backtracking, then fills each until one solves. Because
the layout search and the fill are both complete, "no grid" is a proof, not a
timeout. Word lists longer than 5 (for full-size 15×15 grids) are the remaining
step — see `docs/open-questions.md`.

**Symmetry is optional.** By default the layout search is restricted to
180°-symmetric grids (the crossword convention), where a black cell is chosen as
a *rotation orbit* — so a symmetric grid can only carry an odd black count when a
centre cell absorbs it, and often not even then (a centre black on a 5×5 splits
the middle row/column into length-2 runs, so *no* symmetric 3-black 5×5 exists).
Pass `symmetric=False` (`--nonsymmetric` on `generate.py`) and each cell is its
own unit: any legal placement is allowed, which is the only way to get e.g. 3
black cells across a 5×5. The completeness guarantee is unchanged — the search
just enumerates a larger legal set.

**Capstone — the sampler returns, for the layout (D27).** The epilogue above retired
the stochastic sampler because the *fill* is a hard-bar CSP where complete search wins.
But the black-cell **layout** is the opposite regime: a translation-invariant grid with
*local* run-length legality and a *soft* objective (density, spread, no 2×2 block) — a
field with local factors, and it even stiffens near a critical density (a SAT/UNSAT phase
transition) exactly where the complete search's node budget starts to choke. So an
**annealed-Gibbs sampler over the black-cell field** (`gibbs_layout.py`) is the sampler's
real home — symmetry by construction, connectivity as a global reject, the soft aesthetics
as energy terms. Measured head-to-head against the complete `gen_capped` (D27,
`scripts/gibbs.py`): it *guarantees* no 2×2 block (the complete search emits ~1 in 4),
spreads blacks better, and stays productive at 12×12 where the complete search collapses —
at the cost of speed and completeness, so the two **coexist** (`generate --gibbs`). The
arc's final shape: **stochastic sampling lost the fill and won the layout** — the right
tool for each regime.

## Layout

The package is a hexagon (ports & adapters) with a linear import stack enforced by
import-linter: `core < app < adapters < bootstrap < cli` (see
`docs/architecture.md`).

| Path | What |
|------|------|
| `src/puzzledesk/core/lexicon.py`    | word storage; `set` for column checks, `(M,N)` letter matrix for pattern queries, per-word scores, `filtered(bar)`, `matching(pattern)`, text parsers; `MultiLexicon` buckets words by length for blocked grids |
| `src/puzzledesk/core/square.py`     | double-word-square representation and energy (the fully-checked model) |
| `src/puzzledesk/core/blocked.py`    | **blocked grids** — parse a black-cell pattern into the across/down slot + crossing graph |
| `src/puzzledesk/core/validate.py`   | acceptance test — bottleneck (weakest-word) verdict |
| `src/puzzledesk/core/rng.py`        | the `Rng`/`RngFactory` ports — randomness is injected, not built in the kernel |
| `src/puzzledesk/core/engines/backtrack.py`  | **complete** prefix-pruned search — the engine for squares |
| `src/puzzledesk/core/engines/fill.py`       | **complete** MRV backtracking fill over slots — the blocked-grid engine (+ `enumerate_fills` ground truth) |
| `src/puzzledesk/core/engines/patterns.py`   | **block-pattern generation** — from a black-cell *count* (D13) or a *length cap* (`gen_capped`, D24/D25) to legal layouts; `fill_by_count`/`fill_capped` tie layout search to fill |
| `src/puzzledesk/core/engines/gibbs_layout.py` | **layout field sampler** (D27) — annealed Gibbs over the black-cell field (density/spread/no-2×2), coexisting with the complete search; `fill_gibbs` ties it to fill |
| `src/puzzledesk/core/engines/bruteforce.py` | exhaustive enumeration (ground truth, tiny orders) |
| `src/puzzledesk/app/`               | use-case services (`MiniService`, `BlockedGenerateService`, `ClueService`/`PuzzleService` for clues, `SolveService` for the agent probe, `difficulty` analysis), the ports they need (`LexiconSource`, `Writer`, `ClueProvider`, `SolverAgent`), and structured results |
| `src/puzzledesk/adapters/claude_clue.py`, `claude_solver.py` | the live Claude adapters behind the clue and solver ports (optional `clue` extra; D16/D26) |
| `src/puzzledesk/adapters/`          | infrastructure implementing the ports: `NumpyRngFactory` (the injected Prng), `FileLexicon` (disk reads), `StreamWriter` |
| `src/puzzledesk/bootstrap/`         | composition root — `build()` a service `Container` in stages (config → adapters → services) |
| `src/puzzledesk/cli/`               | thin entry points: argv → build → run → present |
| `tests/`                            | pytest suite — invariants, ground truth, DI (fakes for the ports) |
| `scripts/mini.py`, `generate.py`, `puzzle.py`, `solve.py` | tool shims (logic in `cli/`); also `uv run mini/generate/puzzle/solve …`. `puzzle` clues a whole grid (D20); `solve` runs the agent probe (D26) — both need the `clue` extra + a key |
| `scripts/demo.py`              | validation across N=2..4, `backtrack ⊆ bruteforce` at N=2 (benchmark driver) |
| `scripts/ceiling.py`           | how high can the bar go before UNSAT (`ceiling.py 5 cw`) |
| `scripts/blackcells.py`        | **blocked-grid fill** — ground-truth check, filled grids, quality ceiling |
| `scripts/largemini.py`         | **large capped minis** (D24) — why the count-driven search can't cap, the cap-driven black-count/timing, and fill rate at 10×10/12×12 |
| `scripts/gibbs.py`             | **layout sampler head-to-head** (D27) — Gibbs field vs the complete `gen_capped` on density/spread/2×2/diversity/fill |
| `scripts/difficulty.py`, `solve_effort.py` | difficulty measurement drivers — structural/solve-order openness (D21/D22), and the solver reasoning-effort sweep (D26) |
| `data/words_N.txt`             | length-N words from dwyl `words_alpha` |
| `data/scored_N.txt`            | the above with wordfreq Zipf scores (weak baseline list) |
| `data/cw_N.txt`                | curated crossword list, scored 0–100 (the real list) |
| `data/SOURCES.md`              | provenance and licenses for the word lists |

## Run

The project uses [uv](https://docs.astral.sh/uv/). `uv run` provisions the
virtualenv (installing `puzzledesk` and its deps) on first use, so no manual
`pip install` step is needed.

```bash
uv run scripts/demo.py             # correctness across N=2..4
uv run scripts/mini.py 5 70 3      # three 5x5 minis, every word score >= 70
uv run scripts/ceiling.py 5 cw     # 5x5 quality ceiling on the curated list
uv run scripts/blackcells.py       # blocked-grid fill: ground truth + filled grids
uv run scripts/generate.py 5 5 4 60 3   # 5x5 minis with 4 black cells, layout found by search
uv run scripts/generate.py 5 5 3 60 3 --nonsymmetric  # 3 black cells, no 180° symmetry
uv run generate 10 10 0 60 3 --max-len 5  # a 10x10 capped-entry mini (D24/D25)
```

The clued-puzzle and agent-solver tools need the `clue` extra and an API key
(`uv sync --extra clue`; the key env var defaults to `ANTHROPIC_API_KEY_TWO`, D17):

```bash
uv run --extra clue puzzle --reveal   # a whole clued puzzle as plain text (D20)
uv run --extra clue solve  --reveal   # a Claude agent solves a generated puzzle (D26)
```

`wordfreq` is only needed to regenerate the scored word lists; install it with
the `scoring` extra and run the generator:

```bash
uv run --extra scoring scripts/gen_scored.py   # rebuild data/scored_N.txt
```

## Development

```bash
uv sync                # create/refresh the dev environment
uv run ruff check      # lint
uv run ruff format     # format
uv run mypy            # type-check src/puzzledesk
uv run lint-imports    # enforce the hexagonal layers (import-linter)
uv run pytest          # invariants + ground truth + DI
```

Ruff (lint + format), mypy, import-linter and pytest are configured in
`pyproject.toml`. The package ships type information (`py.typed`); `mypy` runs with
`disallow_untyped_defs`, so new code in `src/puzzledesk` must be fully annotated.
`lint-imports` fails the build on a forbidden cross-layer import, so the
architecture is a checked fact, not a convention.

## Deeper docs (agent-facing, in `docs/`)

- `docs/architecture.md` — data model, invariants, the engines, gotchas
- `docs/decisions.md` — decision log (why it is shaped this way)
- `docs/open-questions.md` — unresolved questions and next-spike considerations
- `docs/notes.md` — benchmarks, environment quirks, data provenance/regeneration

## Status / next

- [x] Lexicon, energy model, brute-force ground truth
- [x] Validated N=2 (vs. ground truth), 3, 4, 5
- [x] Acceptance test as the feedback signal; quality → feasibility on a filtered list
- [x] Complete backtracking engine — non-distinct 5×5 in ~15 ms; on the distinct
      problem ~50–80× over the (original) sampler and complete where the sampler stalled
- [x] 10-distinct-words constraint (forbid the symmetric basin) in test, backtracker,
      and blocked-grid fill
- [x] Mapped the frontier and honest ceiling (distinct 5×5 tops out ~zipf≥3.5;
      ≥4.0 provably UNSAT on the weak list)
- [x] **Retired the sampler** (D19) — the original stochastic engine lost the
      head-to-head to complete search; removed with its benchmark drivers, verdict
      recorded in `docs/decisions.md`/`docs/notes.md`
- [x] **Curated lexicon** — swapped in the Crossword-Nexus list; distinct 5×5
      minis with every word ≥90, publishable fills. `scripts/mini.py` generates.
- [x] **Black cells** — slot/crossing model + complete MRV backtracking fill;
      varying-length slots, distinct entries, every entry ≥ bar; tiny grid vs
      brute-force ground truth. `scripts/blackcells.py`. (Fill only.)
- [x] **Block-pattern generation** — black cells are a *count*, not a template;
      `patterns.py` searches legal symmetric/checked/connected layouts and fills
      them, complete both ways (`scripts/generate.py`)
- [x] **Non-symmetric black cells** — `symmetric=False` drops the 180° constraint
      so any legal placement is allowed (e.g. 3 blacks across a full 5×5, which no
      symmetric layout admits); `generate.py --nonsymmetric`
- [x] **Hexagonal architecture** — pure `core`, `app` services, `adapters` (the
      injected Prng lives here), a staged `bootstrap` container, thin `cli`; layering
      enforced by import-linter; pytest suite driven by injected fakes (D14)
- [x] **Clue generation** — the `ClueProvider` port + `FilledGrid` anti-corruption
      form (D15), a live Claude adapter behind it (D16), and the whole-puzzle compose
      (`PuzzleService` + a plain-text solving view; `uv run puzzle`, D20). Clue
      *quality* is still iterating; the pipeline ships.
- [x] **Difficulty modelling** — the *complete, deterministic* slices: a two-sided
      obscurity band (D21 layer A), static open-crossing / Natick checkability
      (`analyze`, D21 A′) and the dynamic solve-order cascade (`solve_order`, D22), plus
      generate-to-a-difficulty (`mini --hard K`, D23). The soft/clue layers stay
      recorded-but-unbuilt pending human solve data.
- [x] **Agent solve probe** — a Claude agent solving a generated puzzle in a feedback
      loop as an empirical difficulty signal (`uv run solve`, D26); reasoning-token
      spend is the graded tell (see `docs/notes.md`)
- [x] **Large capped minis** — cap the *maximum* entry length so a 10×10 fills from
      the 2..5 lists (`gen_capped`, D24), with density control (a white-biased search +
      a black-cell ceiling, D25); `generate --max-len K`
- [x] **Layout field sampler** — an annealed-Gibbs sampler over the black-cell field
      (density/spread/no-2×2), measured against the complete search and *kept, scoped*:
      the sampler lost the fill (D19) and won the layout (D27); `generate --gibbs`
- [x] **Basin-shape × count study** (D28) — swept grid size, density, and energy weights:
      the count knob has a jamming floor, the failure mode shifts to run-length legality as
      the grid grows, and the connectivity *repair* was tried and **removed** (defeated by
      the cap — the separating blacks are cap-load-bearing); `scripts/gibbs.py`
- [ ] Word lists longer than 5 — needed for full-size (15×15) blocked grids
- [ ] Clue *quality* + calibration — ranking, cross-clue constraints, and a
      calibrated Mon..Sat target (needs human solve logs; D21 layers B/C)
- [ ] Grid variety controls — seed words, themes, avoid overused entries
- [ ] Past the legality wall (>12×12) — ASP-native connectivity or a run-length-aware move
      set (WFC), + a spread/density preset surface over `FieldParams` (the open D28 threads)
- [ ] JAX parallel chains — only if the layout field sampler (D27) needs the scale
