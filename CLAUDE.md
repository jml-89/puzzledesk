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

## The four layers

Code here divides into four layers with different rules. Keep the boundaries
sharp; most review friction comes from smearing them.

### kernel — `src/puzzledesk/`

The pure library: the two grid models, the engines, the lexicon. Rules:

- **No I/O.** No `print`, no argv, no reading files except through an explicit
  path argument (`Lexicon.from_scored_file(path, …)`). `render`/`column_strings`
  *return* strings; they do not print them.
- **Deterministic given a seed.** All randomness goes through
  `np.random.default_rng(seed)`. No unseeded `random`, no wall-clock, no
  `Math.random`-equivalent. A `(lists, seed)` pair reproduces a result exactly.
- **Fully typed.** `mypy` runs here with `disallow_untyped_defs`; the package
  ships `py.typed`. New code is fully annotated, no exceptions.
- Carries the invariants below. This is where correctness lives.

### shell — the I/O boundary

The thin layer that turns kernel values into bytes and back: argv parsing, file
loading, rendering, `stdout`. Today this is **smeared into each script's
`__main__`** rather than being a module; that is a known wart, not the target.
When you touch it, keep I/O *here* and keep the kernel pure — do not push a
`print` down into `src/`.

### tools — user-facing generators (`scripts/`, artifact producers)

Programs a user runs to *get a crossword*: `mini.py`, `generate.py`,
`blackcells.py`. They should be tight, produce artifacts, and every grid they
emit must pass the acceptance test (invariant 3, below). A tool is an **output
path**.

### benchmarks — measurement drivers (`scripts/`, number producers)

Programs that *measure*, not produce: `bench.py`, `ceiling.py`, `frontier.py`,
`compare.py`, `samplers.py`, `quality.py`. They may be slow, throwaway, and
loosely typed (`scripts/*.py` are `ANN`-exempt in ruff on purpose). Their output
is numbers for `docs/notes.md`, not grids for a user.

> Tools and benchmarks currently share the `scripts/` directory and each script
> hand-rolls its own `sys.path`/argv handling. Splitting them (a `scripts/tools`
> vs `scripts/bench` layout, and/or `[project.scripts]` console entry points) is
> a deliberate follow-up, not done here. Until then, honour the distinction by
> *intent* even though the files sit together.

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
uv run scripts/mini.py 5 70 3          # a tool: three distinct 5x5 minis, every word >= 70
uv run scripts/ceiling.py 5 cw         # a benchmark: the 5x5 quality ceiling
```

- **Ruff is authoritative.** Do not argue with it or scatter `# noqa`; fix the
  code or change the shared config in `pyproject.toml` with a reason. The `select`
  set is broad on purpose (`E W F I UP B C4 SIM ANN RUF`).
- **`wordfreq` is optional**, needed only to regenerate `data/scored_N.txt`:
  `uv run --extra scoring scripts/gen_scored.py`. The solvers read the files, not
  `wordfreq`.
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

## Tests as contracts (target state — not yet wired)

There is **no `tests/` directory and pytest is not yet a dependency** (though
`.pytest_cache/` is already git-ignored in anticipation). Today the contracts are
asserted ad hoc inside scripts: `demo.py` checks the sampler against N=2
brute-force ground truth, `generate.py` asserts the layout invariants, `mini.py`
asserts `validate(...).ok`. The intended direction is to promote these into a
real pytest suite where **each test encodes an invariant**:

- ground-truth subset: solver output ⊆ `bruteforce` / `enumerate_fills`
  enumeration at N=2 and on the tiny blocked grid (small-first, made permanent);
- completeness: a known-UNSAT case (weak-list distinct 5×5 at `zipf≥4.0`) returns
  `None` — the proof is a test;
- distinctness: every output path's grids pass `validate` with `n_distinct == 2N`.

Two rules for when the suite exists:

- **Tests assert correctness/contracts; benchmarks measure.** Keep wall-clock out
  of tests — the timings in `docs/notes.md` are explicitly order-of-magnitude and
  container-dependent, so any timing assertion would be flaky.
- Add pytest to the `dev` dependency group, not the runtime deps.

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
