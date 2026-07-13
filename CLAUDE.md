# CLAUDE.md

Operating manual for an agent working in this repo. It tells you how the code is
*layered*, which invariants are load-bearing, and how to use the toolchain. It
does **not** restate the design — that lives in `docs/`, and you should read it:

- `docs/roadmap.md` — the chosen forward **direction** (D34): ship a playable product and
  close the human-solve loop. The one forward-looking doc; everything else here is memory.
- `docs/architecture.md` — data model + the numbered invariant list (0–5). Authoritative.
- `docs/decisions.md` — ADR-style decision log (D1–D36). *Why* it is shaped this way.
- `docs/notes.md` — benchmarks, environment quirks, data provenance/regeneration.
- `docs/open-questions.md` — unresolved questions and next-spike candidates.
- `docs/postmortem-kernel-methods.md` — the D31 review-of-methods spike (solution
  counting + distinctness pruning), measured and tombstoned. Read before re-attempting
  either, and for a synthesis of the whole methods arc.
- `docs/lesson-length-ceiling.md` — why the 2..5 word-length ceiling was a *data* accident,
  not a design limit (closed at D36), and the load-bearing distinction between **max word
  length** (vocabulary → less-dense grids) and **double-square order** (density/search).
  Read before reasoning about grid size or "how long a word can we hold"; it indexes the
  older, assumption-laden decisions so you read them right.
- `CONTRIBUTING.md` — branch/commit/PR etiquette. Read before you push.

When this file and `docs/architecture.md` seem to disagree, `architecture.md`
wins and this file is stale — fix it.

## The layers (hexagonal; enforced — D14)

`src/puzzledesk/` is a hexagon with a **linear** import stack, and it is no longer
a convention: **import-linter** (`uv run lint-imports`) fails the build on a
forbidden edge. A layer may import any layer *below* it, never one above:

    core  <  app  <  adapters  <  bootstrap  <  cli  <  web

(`cli` and `web` are sibling entry points — argv and HTTP; the contract stacks `web`
on top and neither imports the other. `web` is behind a `web` extra — D35.)

Keep the boundaries sharp; the linter is what keeps them so. Full detail lives in
`docs/architecture.md` §"Layered architecture" and `docs/decisions.md` D14.

### core — the pure kernel (`src/puzzledesk/core/`)

The two grid models, the engines, the lexicon, `validate`. Rules:

- **No I/O.** No `print`, no argv, **no reading files** (the kernel now *parses
  text* — `Lexicon.from_scored_text`/`from_words_text` — and the `FileLexicon`
  adapter does the read). `render`/`column_strings` *return* strings.
- **Deterministic, randomness injected.** Engines take an `rng` (the `core.rng.Rng`
  port), they do **not** open their own `np.random.default_rng`. Still no unseeded
  `random`, no wall-clock. A `(lists, seed)` pair reproduces a result exactly —
  `NumpyRngFactory.create(seed)` is `default_rng(seed)`, so injection changed the
  wiring, not the numbers. The *observation* mirror is the `core.probe.Probe` port
  (D37): the engines emit structured events (`fill`/`gen_capped`/`fill_capped` do now),
  observe-only and no-op by default, so a watcher cannot change the search — adapters
  (`LoggingProbe`/`HeartbeatProbe`) render them.
- **Fully typed** (`mypy`, `disallow_untyped_defs`; ships `py.typed`).
- Carries the invariants below. This is where correctness lives.

### app — use-case services + ports (`src/puzzledesk/app/`)

`MiniService` (the square batch), `GenerateService` (one grid for any layout
strategy), `PuzzleService` (the end-to-end compose), and the ports they need from
outside (`app/ports.py`: `LexiconSource`, `Writer`). Services orchestrate the core
through ports and return structured results (`app/results.py`). Generation input is
*modelled*, not a bucket of kwargs: `app/spec.py` holds the typed request algebra —
`GridSpec` + a closed `LayoutStrategy` union (`FullSquare`/`CountLayout`/`CappedLayout`/
`GibbsLayout`) + `FillSpec`, bundled as `PuzzleSpec` — dispatched with `match` +
`assert_never` (D32). **They must not import a
concrete adapter, read a file, or print** — that inversion is the whole point and
the linter enforces it (`app → adapters` is a broken contract). The two *soft*
LLM-backed stages live here too, each fenced behind a port with the model in an
adapter: cluing (`ClueProvider` → `ClueService`, D15/D16) and solving (`solve.py`
session + `SolverAgent` → `SolveService`, D26 — a Claude agent solving in a feedback
loop, as an empirical difficulty probe).

### adapters — infrastructure (`src/puzzledesk/adapters/`)

Where effects are bound: `NumpyRngFactory` (the injected Prng — `default_rng` lives
only here), `FileLexicon` (the disk read), `StreamWriter`. They
sit *above* app because they implement app's ports. Keep new I/O *here*, never in
`core`/`app`.

### bootstrap + cli + web — composition root and the fronts

`bootstrap.build()` assembles a `Container` in three stages (config → adapters →
services). `cli/` are thin entry points (argv → build → run → present); the tools
`mini`/`generate`/`puzzle`/`solve` are typed `cli` modules with `scripts/*.py` shims (and
`[project.scripts]` console commands). A tool is an **output path** — every grid it
emits passes the acceptance test (invariant 3).

`web/` is the HTTP front (D35), a sibling of `cli` over the same container: `POST /puzzles`
(a Pydantic wire body → `PuzzleSpec` → generate → store → JSON view) and `GET /puzzles/{id}`.
It is fenced behind a `web` extra (FastAPI/Pydantic), isolated like `anthropic` behind
`clue` — the package and the whole gate run without it. Persistence is the `app.repository`
`PuzzleRepository` port (in-memory adapter now, a DB later — the roadmap's Phase 1). The
completeness tag crosses the wire (a `None` becomes 422 `unsat` vs `budget`, per D32).

### benchmarks — measurement drivers (`scripts/`, number producers)

`ceiling.py`, `demo.py`, `blackcells.py`, `difficulty.py`, `largemini.py`, `gibbs.py`,
`scan.py`, `spike_probe.py`, `solve_effort.py`: they *measure/demo*, not produce. They stay loose and `ANN`-exempt
(`scripts/*.py`), but now `build()` the container and drive the core engines through its
injected `lexicon`/`rng_factory` adapters — no bare `default_rng`/`DATA` path. Their
output is numbers for `docs/notes.md` (see architecture.md "Benchmark/demo drivers" for
the full list). (The sampler-only drivers `bench`/`frontier`/`compare`/`samplers`/
`quality` were removed with the sampler engine — D19.)

> Still a follow-up: splitting tool vs benchmark *directories* and console entry
> points for every driver. `cli` groups them by intent; honour the distinction.

## Load-bearing invariants

The full list with rationale is `docs/architecture.md` §"Invariants — do not
break" (0–5). Do not duplicate it here — read it there. The three that catch
agents most often:

- **`None` is a proof, not a timeout.** The engines are *complete*: when
  `backtrack.solve` / `fill.solve` / `patterns.fill_by_count` return `None`, the
  tree is exhausted and **no** acceptable grid exists for those lists at that bar
  — a genuine UNSAT theorem. Never catch it and "give up," never paper over it
  with a retry budget, never describe it as a timeout. This epistemics (a ceiling
  becomes a theorem) is the point of the whole design.
- **Distinctness gates every output path.** Acceptable output has 2N distinct
  words (invariant 3). It is enforced in `validate`, `backtrack`, and `fill` (the
  blocked-grid engine's grid-wide `used` set). **If you add a new emitter, it must
  enforce distinctness** or the symmetric basin returns.
- **Score scale is per-list.** `scored_N.txt` is wordfreq Zipf (~0–8);
  `cw_N.txt` is crossword 0–100 (invariant 4). A threshold means nothing across
  lists. Never reuse a bar from one list on the other.

## Toolchain

Everything runs through [uv](https://docs.astral.sh/uv/); `uv run` provisions the
env on first use, so there is no manual `pip install`.

```bash
uv sync                 # create/refresh the dev environment
uv run ruff check       # lint (authoritative — the config in pyproject.toml is the rulebook)
uv run ruff format      # format
uv run mypy             # type-check src/puzzledesk (strict: disallow_untyped_defs)
uv run lint-imports     # architecture: the hexagonal layers contract (import-linter)
uv run pytest           # tests: invariants + ground truth + DI (see below)
uv run --extra web pytest              # ...also runs the web-layer tests (else importorskip'd)
uv run scripts/mini.py 5 70 3          # a tool: three distinct 5x5 minis, every word >= 70
uv run mini 5 70 3                     # ...same, via the console entry point
uv run --extra clue puzzle --reveal    # a tool: a whole clued puzzle as plain text (D20; needs a key)
uv run --extra clue solve --reveal     # a tool: a Claude agent solves a generated puzzle (D26; needs a key)
uv run generate 10 10 0 60 3 --max-len 5   # a tool: 10x10 minis, entries capped at 5 (D24)
uv run generate 10 10 0 65 2 --max-len 5 --gibbs  # a tool: capped minis, layout from the Gibbs field (D27)
uv run --extra web uvicorn puzzledesk.web.main:app  # the HTTP API: POST/GET /puzzles (D35)
uv run scripts/ceiling.py 5 cw         # a benchmark: the 5x5 quality ceiling
uv run scripts/largemini.py            # a benchmark: the large capped-mini spike (D24)
uv run scripts/gibbs.py                # a benchmark: Gibbs layout field vs the complete search (D27)
uv run scripts/scan.py 9 9 6 60 --gibbs --nonsym   # sweep seeds, rank fills by weakest word (D27)
uv run scripts/spine.py 62 400 8       # a benchmark: mint "one-spine wonder" Latent grids (D39)
uv run python site/build_latent_long.py   # rebuild a Latent variant page (site/, D39)
```

### Generation cheatsheet — which lever for which grid

Two questions burn time if you don't know them up front: *which engine for the grid I want*,
and *why is a run hanging*. The distinctions (full detail in `docs/lesson-length-ceiling.md`
and architecture.md §"Blocked grids"/"Cap-driven layouts"):

- **Dense square** (`mini` / `FullSquare`): every row *and* column a full word. Complete, but
  gated by **double-square order rarity** — 5×5 is the reliable ceiling, 6×6+ get rare fast in
  English. Longer word lists do **not** push this; it's a density/search frontier, not data.
- **A word longer than 5** is the *other* axis — pure vocabulary. The lists run to length 15
  (D36), so just raise the **cap** (`--max-len K`). This is the length-ceiling lesson's whole
  point: "how long a word can we hold" ≠ "how dense a square can we build."
- **Big grid, hold entries short → cap-driven** (`generate R C 0 min N --max-len K`): caps the
  *max* entry length with black cells, prunes run-length as it searches, fast to ~10×10.
  **Bound the black count** (`--max-black`, or a fixed count) — an *unbounded* `max_black` at
  large N makes the layout search explode (this is a top hang cause).
- **Fix a black *count* → count-driven** (`generate R C K min N`): caps only the *minimum*
  length, so it leaves full-width runs. On a big/dense grid those long checked runs hit the
  **word-square rarity wall** — slow or a real UNSAT. Fine for small grids / few blacks; a poor
  choice when you want long entries in a big grid (use the cap instead).
- **Nicer texture → Gibbs** (`--gibbs`, cap mode): sampled layout, guaranteed no 2×2 block,
  supports `--nonsymmetric`. Not complete — a miss is *budget exhaustion, not a proof*.
- **Picking a clean sample:** don't hand-roll a seed sweep — `scripts/scan.py` ranks seeds by
  the **weakest word** (the acceptance bottleneck, invariant 4). `generate … count>1` also
  prints each grid's scored words. Score bars are per-list (invariant 4).

- **Ruff is authoritative.** Do not argue with it or scatter `# noqa`; fix the
  code or change the shared config in `pyproject.toml` with a reason. The `select`
  set is broad on purpose (`E W F I UP B C4 SIM ANN TID RUF` plus the D39 modern-idiom
  ratchet — `FURB FA RET PIE PTH SLOT ISC LOG G PERF PLC PLE PLW`; the `pyproject.toml`
  comment records what was deliberately left out and why). `TID`
  (`ban-relative-imports = "all"`) means **imports are absolute (`puzzledesk.*`),
  never relative** — Ruff enforces the *spelling* of an import, import-linter the
  *architecture*; both are structural, not review conventions. It is auto-fixable.
- **import-linter is authoritative for the architecture.** Two contracts in
  `pyproject.toml` (`[tool.importlinter]`) *are* the boundary spec: the `layers`
  contract (D14) and a `forbidden` contract keeping the OS (`os`/`io`/`sys`/
  `subprocess`/`socket`) out of the pure `core`/`app` layers — the environment is
  grabbed once in `bootstrap`, never in the kernel (D18). If you genuinely need a new
  cross-layer edge, change the contract with a reason (a D-entry if it reshapes the
  architecture) — do not route around it.
- **Word data is generated, lengths 2..15** (D36). Three reproducible drivers, each
  `--min-len/--max-len`: `scripts/gen_cw.py` (curated `cw_N`, the default list) and
  `scripts/gen_words.py` (plain `words_N`) slice their upstreams; `scripts/gen_scored.py`
  scores `words_N` with wordfreq. The solvers read the committed files, never the sources.
- **`wordfreq` is optional**, needed only to (re)generate `data/scored_N.txt`:
  `uv run --extra scoring scripts/gen_scored.py`.
- **`anthropic` is optional** (`clue` extra), needed only for *live* clue generation
  (`adapters/claude_clue.py`); it is imported lazily and resolves the API key from the
  environment. The grid generator and tests run without it (the `FakeClueProvider`
  drives the clue pipeline). `uv sync --extra clue` + `ANTHROPIC_API_KEY` to go live.
- In CI or any reproducible run, prefer `uv sync --frozen` / `uv run --frozen` so
  the committed `uv.lock` is honoured rather than silently resolved.

## Modern Python — the floor is 3.13

The house style is modern: `from __future__ import annotations`, PEP-604 `X | None`,
`@dataclass`, `pathlib`, keyword-only args (`def solve(sq, *, …)`). Keep it. Reach
further where it buys clarity or immutability:

- `@dataclass(slots=True, frozen=True)` for value types (verdicts, slot/grid records);
- `match` + `typing.assert_never` for dispatch over closed unions (the two coexisting
  grid models, the `LayoutStrategy` union) — the stdlib one, imported directly;
- `Protocol` for the shared engine surface (a `solve(...) -> state | None`).

**The floor:** `requires-python = ">=3.13"`, ruff `target-version = "py313"`, mypy
`python_version = "3.13"` (D33). 3.10 was security-only and is retired. The whole 3.11–3.13
toolbox is now *in bounds* — `typing.assert_never`, `StrEnum`, `tomllib`, PEP-695
`type X = …` alias / `class Foo[T]` generic syntax, `@typing.override`. Use them where they
earn it (the old `NoReturn` `assert_never` shim from D32 is gone — `typing.assert_never`
replaced it). Raising the floor again (e.g. to 3.14 once the environment can provision and
verify it) is a deliberate D-entry decision, not a drive-by — but there is no longer a
sub-3.13 boundary to police.

## Tests as contracts (wired — D14)

There is a **`tests/` suite** (`uv run pytest`; pytest is in the `dev` group), and
**each test encodes an invariant**, driven with injected fakes (`tests/fakes.py`:
an in-memory `LexiconSource`, a recording `RngFactory`) so the pure code runs with
no files and no global RNG:

- ground-truth subset (`test_ground_truth.py`): solver output ⊆ `bruteforce` /
  `enumerate_fills` enumeration on tiny in-memory lexicons;
- layout search (`test_patterns.py`): `gen_patterns` == brute force on a small case
  (was `generate.py`'s inline property-check);
- completeness (`test_invariants.py`): a known-UNSAT case (the `{ab,ba}` symmetric
  basin) returns `None` — the proof is a test;
- distinctness (`test_invariants.py`, `test_services.py`): output has
  `n_distinct == 2N`;
- ports/DI (`test_rng_port.py`, `test_services.py`): numpy satisfies `Rng`; the
  services are reproducible and use the injected factory.

Two standing rules:

- **Tests assert correctness/contracts; benchmarks measure.** Keep wall-clock out
  of tests — the timings in `docs/notes.md` are order-of-magnitude and
  container-dependent, so any timing assertion would be flaky.
- The `demo.py`/`blackcells.py` drivers keep runnable copies of the ground-truth
  checks; the tests are the gate. If you change a contract, update both.

## Keep the docs in sync — this is a workflow rule, not a nicety

The docs are the repo's memory and they are good; do not let them rot.

- A **design decision** (a new engine, a changed invariant, a scope call) gets a
  new **`D14`+** entry *appended* to `docs/decisions.md`. Do not rewrite history;
  the reversal notes are load-bearing.
- Touching an **invariant or the data model** ⇒ update `docs/architecture.md`.
- A new **benchmark number or environment quirk** ⇒ `docs/notes.md`.
- Resolving or raising an open question ⇒ `docs/open-questions.md`.

If a change would make any statement in `docs/` false, the doc edit is part of
the change, not a follow-up.
