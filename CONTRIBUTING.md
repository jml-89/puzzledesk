# Contributing

How changes get into this repo. It reflects the pattern the history already
follows (PRs #1–#5) rather than inventing ceremony. For *how the code is
layered and what invariants hold*, read `CLAUDE.md` and `docs/architecture.md`
first — this file is only about the mechanics of a change.

## One concern per PR

Each PR is a single spike or fix, the way the log reads today ("Adopt uv,
package the project, add ruff + mypy", "Generate block patterns from a
black-cell count"). If you find yourself writing "and also" in the description,
it is two PRs. Small, reviewable, self-consistent.

## Branches

- Work on a topic branch named `claude/<short-slug>` (e.g.
  `claude/black-cells-parameters`). Never commit directly to `main`.
- `main` is the mainline and the GitHub default branch. (It was briefly not —
  see D10 / `docs/notes.md` for the empty-repo history.)
- If the PR for your branch has already merged, treat follow-up work as a fresh
  change: restart the branch from the latest `main` rather than stacking new
  commits on merged history.

## Before you push — the gate

All three must be green. Do not push red and "fix it in the next commit."

```bash
uv run ruff check     # lint
uv run ruff format    # format (run it; don't hand-format)
uv run mypy           # types — strict on src/puzzledesk
```

When a test suite exists (see `CLAUDE.md` → "Tests as contracts"), add
`uv run pytest` to this gate. Until then, run the relevant script whose inline
assertions cover your change (e.g. `uv run scripts/demo.py` after touching the
energy model or sampler; `uv run scripts/generate.py …` after touching layout
generation).

## Commits

- Imperative subject line, matching the existing log: "Add …", "Adopt …",
  "Generate …", "Refine …". Describe the change, not the process.
- Keep commits coherent; a reviewer should be able to read the series.

## Documentation is part of the change

The docs are the repo's memory (`docs/`). A change that outdates them is
incomplete:

- A **design decision** ⇒ append a new **`D14`+** ADR entry to
  `docs/decisions.md` (append, never rewrite — reversal notes are load-bearing).
- An **invariant or data-model** change ⇒ update `docs/architecture.md`.
- A **benchmark result or environment quirk** ⇒ `docs/notes.md`.
- A resolved/raised open question ⇒ `docs/open-questions.md`.

## Pull requests

- **Do not open a PR unless it was explicitly asked for.** Push the branch; let a
  PR be requested.
- When you do open one: a title in the same imperative style, and a body that
  says *what changed and why* — link the relevant `Dn` decision if the change
  carries one. Keep it to the diff; do not paste credentials, tokens, internal
  hostnames, or environment details.
- Don't reuse a merged PR for new work (see "Branches").

## Non-negotiables (from `CLAUDE.md`)

A reviewer will bounce a PR that breaks these, so check yourself first:

- A **new grid-emitting path enforces distinctness** (invariant 3) — or it
  resurrects the symmetric basin.
- **`None` from a solver is a UNSAT proof**, never swallowed as a timeout.
- **No 3.11+-only features** while the floor is `>=3.10` (raising it is a
  D-entry decision).
- The **kernel stays pure** — no I/O pushed into `src/puzzledesk/`.
