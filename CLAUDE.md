# CLAUDE.md

Operating manual for an agent working in this repo. It tells you how the code is
*layered*, which invariants are load-bearing, and how to use the toolchain. It
does **not** restate the design — that lives in `docs/`, and you should read it:

- `docs/architecture.md` — data model + the numbered invariant list (0–5). Authoritative.
- `docs/decisions.md` — ADR-style decision log (D1–D13). *Why* it is shaped this way.
- `docs/notes.md` — benchmarks, environment quirks, data provenance/regeneration.
- `docs/open-questions.md` — unresolved questions and next-spike candidates.
- `CONTRIBUTING.md` — branch/commit/PR etiquette. Read before you push.

When this file and `docs/architecture.md` seem to disagree, `architecture.md`
wins and this file is stale — fix it.

## The layers (hexagonal; enforced — D14)

`src/puzzledesk/` is a hexagon with a **linear** import stack, and it is no longer
a convention: **import-linter** (`uv run lint-imports`) fails the build on a
forbidden edge. A layer may import any layer *below* it, never one above:

    core  <  app  <  adapters  <  bootstrap  <  cli

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
  wiring, not the numbers.
- **Fully typed** (`mypy`, `disallow_untyped_defs`; ships `py.typed`).
- Carries the invariants below. This is where correctness lives.

### app — use-case services + ports (`src/puzzledesk/app/`)

`MiniService`, `BlockedGenerateService`, and the ports they need from outside
(`app/ports.py`: `LexiconSource`, `Writer`). Services orchestrate the core through
ports and return structured results (`app/results.py`). **They must not import a
concrete adapter, read a file, or print** — that inversion is the whole point and
the linter enforces it (`app → adapters` is a broken contract).

### adapters — infrastructure (`src/puzzledesk/adapters/`)

Where effects are bound: `NumpyRngFactory` (the injected Prng — `default_rng` lives
only here), `FileLexicon` (the disk read), `StreamWriter`/`CapturingWriter`. They
sit *above* app because they implement app's ports. Keep new I/O *here*, never in
`core`/`app`.

### bootstrap + cli — composition root and the front

`bootstrap.build()` assembles a `Container` in three stages (config → adapters →
services). `cli/` are thin entry points (argv → build → run → present); the tools
`mini`/`generate` are typed `cli` modules with `scripts/*.py` shims (and
`[project.scripts]` console commands). A tool is an **output path** — every grid it
emits passes the acceptance test (invariant 3).

### benchmarks — measurement drivers (`scripts/`, number producers)

`bench.py`, `ceiling.py`, `frontier.py`, `compare.py`, `samplers.py`, `quality.py`,
`demo.py`, `blackcells.py`: they *measure/demo*, not produce. They stay loose and
`ANN`-exempt (`scripts/*.py`), but now `build()` the container and drive the core
engines through its injected `lexicon`/`rng_factory` adapters — no bare
`default_rng`/`DATA` path. Their output is numbers for `docs/notes.md`.

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
  words (invariant 3). It is enforced in `validate`, `backtrack`, and the
  `distinct=True` sampler. **If you add a new emitter, it must enforce
  distinctness** or the symmetric basin returns. The sampler's `distinct=False`
  raw-packing default is *not* an output path.
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
uv run scripts/mini.py 5 70 3          # a tool: three distinct 5x5 minis, every word >= 70
uv run mini 5 70 3                     # ...same, via the console entry point
uv run scripts/ceiling.py 5 cw         # a benchmark: the 5x5 quality ceiling
```

- **Ruff is authoritative.** Do not argue with it or scatter `# noqa`; fix the
  code or change the shared config in `pyproject.toml` with a reason. The `select`
  set is broad on purpose (`E W F I UP B C4 SIM ANN RUF`).
- **import-linter is authoritative for the architecture.** Two contracts in
  `pyproject.toml` (`[tool.importlinter]`) *are* the boundary spec: the `layers`
  contract (D14) and a `forbidden` contract keeping the OS (`os`/`io`/`sys`/
  `subprocess`/`socket`) out of the pure `core`/`app` layers — the environment is
  grabbed once in `bootstrap`, never in the kernel (D18). If you genuinely need a new
  cross-layer edge, change the contract with a reason (a D-entry if it reshapes the
  architecture) — do not route around it.
- **`wordfreq` is optional**, needed only to regenerate `data/scored_N.txt`:
  `uv run --extra scoring scripts/gen_scored.py`. The solvers read the files, not
  `wordfreq`.
- **`anthropic` is optional** (`clue` extra), needed only for *live* clue generation
  (`adapters/claude_clue.py`); it is imported lazily and resolves the API key from the
  environment. The grid generator and tests run without it (the `FakeClueProvider`
  drives the clue pipeline). `uv sync --extra clue` + `ANTHROPIC_API_KEY` to go live.
- In CI or any reproducible run, prefer `uv sync --frozen` / `uv run --frozen` so
  the committed `uv.lock` is honoured rather than silently resolved.

## Modern Python — with one hard boundary

The house style is already modern: `from __future__ import annotations`,
PEP-604 `X | None`, `@dataclass`, `pathlib`, keyword-only args (`def solve(sq, *,
…)`). Keep it. Reach further where it buys clarity or immutability:

- `@dataclass(slots=True, frozen=True)` for value types (verdicts, slot/grid records);
- `match` + `typing.assert_never` for dispatch over the two coexisting grid models;
- `Protocol` for the shared engine surface (a `solve(...) -> state | None`).

**The boundary:** `requires-python = ">=3.10"` and ruff `target-version =
"py310"`. The dev container runs 3.11, so `StrEnum`, `tomllib`, and PEP-695
`type`/generic syntax will *import locally but break the stated floor*. Do not
use 3.11+-only features until the floor is deliberately raised (that is a D-entry
decision, not a drive-by). "Modern" means modern *within 3.10*.

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
