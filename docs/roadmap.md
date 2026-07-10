# Roadmap — from an engine that *proves* to a service that *is played*

This is the first forward-looking doc in `docs/`. Everything else here is memory —
what was built and why. This is the opposite: the chosen **direction** and the staged
plan to get there, recorded so the direction is durable rather than a decision that
evaporates in a chat. It is the roadmap the direction call in `docs/decisions.md` **D34**
commits to; read D34 for the *why* and this for the *what next*.

It supersedes the "next front" bullets scattered in `docs/open-questions.md`
(the REST API under "Generation specs — BUILT (D32)"; the difficulty calibration
under "Difficulty"): those are no longer loose questions but sequenced work below.

## The goal, in one sentence

Turn puzzledesk from an engine that **proves things about** puzzles into a service
that **serves** them and **learns from being played** — closing the one feedback loop
the project has never closed: *a real human solves a real puzzle, and their solve-time
becomes ground truth.*

## Why this, and why now

The project has two "cybernetic" streams, and both are **internal** loops:

1. **Generation** ("the largest grid without pathological performance"): square →
   count-driven blocked → cap-driven large minis → the Gibbs field sampler (D13/D24–D28).
   The arc is essentially closed; the remaining frontier (WFC, ASP, 15×15, a template
   library) is *more of the same kind of method*.
2. **Difficulty** ("an agent as solver, to measure how hard our minis are"): static
   openness → the solve-order cascade → the live LLM-agent probe (D21/D22/D26).

The loop the system has **never** closed is the **external** one — a person playing.
And that is not a nice-to-have: the difficulty stream is *explicitly, repeatedly blocked
on exactly that signal.* `open-questions.md` says it in a dozen places — "the one thing
that would unblock B and C … is a human solve-time signal to calibrate IRT θ/b against";
"an LLM brackets *a* solver, not *the* distribution." **D26's agent-solver was always a
proxy** for a human signal we do not have.

So shipping a playable product is not merely "a product at the end." It is the
**instrument that produces the missing measurement.** One loop unifies both streams:

    generate (stream 1) → clue → serve → a human plays → solve-time telemetry
      → calibrate difficulty (stream 2, proxy replaced by ground truth) → target better → generate

The architecture has been visibly aiming here: **D32's typed spec algebra was built as
the forcing function for a REST body**, `open-questions.md` already names "*A REST API —
the next front (not built)*" plus a `PuzzleRepository` port, and `site/` already carries
a black-cell-aware player — it is just static, pre-rendered pages today.

The two directions *not* taken, and why (the full argument is D34): more
generation/field methods stays inward and is method-exploration, not a product; an
engineering "revamp" is the lowest-value option — the code is already hexagonal,
strict-typed, DI'd, and import-linted, with little real debt to pay down.

## The discipline this plan honours

The repo's rule (D15) is **"introduce a modelled structure only where an external
contract forces it."** That governs the *sequencing* below: the `PuzzleRepository` port
and any wire schema arrive **with the web layer that forces them**, never speculatively
ahead of it. Each phase is one shippable vertical slice (CONTRIBUTING: "one concern per
PR"), each ends with the five-command gate green, and each carries its own D-entry when it
makes a design call. **`None` stays a proof** across every new seam (the layout tag,
`spec.layout_is_complete`, travels into the API's "no puzzle" response — never a swallowed
timeout).

## Phase 1 — the API seam (pure architecture, no new research)

The forcing contract that makes the rest legal to build. A `web/` entry point beside
`cli/`, reusing `build()`'s container.

- **`app/repository.py`** — a `PuzzleRepository` port (`save`/`get`) over the
  `CluedPuzzle` aggregate (plus a `PuzzleId`). The "Second adapters" seam
  `open-questions.md` reserved, now exercised. *Determinism nuance to encode:* the fill
  is reproducible from `(lists, spec, seed)`, but the **clues are soft (LLM)**, so the
  clued aggregate is stored as data, not regenerated from the spec.
- **`adapters/memory_repository.py`** — an in-memory implementation (a dict). A DB
  adapter is a later, drop-in second implementation of the same port.
- **`web/`** — FastAPI, behind a `web` extra isolated exactly like `anthropic` behind
  `clue` (imported lazily; the package and its gate run without it). A **Pydantic wire
  schema** that *parses into* `PuzzleSpec` — a **separate** object, never `PuzzleSpec`
  itself (D15: the port speaks the canonical form; serialization is an export concern).
  - `POST /puzzles` — JSON → wire schema → `PuzzleSpec` → `PuzzleService.generate` →
    store → return the `CluedPuzzle` as JSON (another *view*, beside `present.playable`).
    A `None` grid → an honest response worded from `layout_is_complete` (proof vs budget).
  - `GET /puzzles/{id}` — read it back.
- **Wiring**: `Container` gains a `repository` field; `bootstrap.build()` constructs the
  in-memory adapter. **import-linter**: `web` joins the `layers` contract at the `cli`
  tier (a top entry point) — a new contract line, changed with a reason, not routed around.
- **Tests**: the round-trip (`POST` then `GET`), the UNSAT/budget response wording, the
  wire-schema → spec parse. Driven with the existing fakes (`FakeClueProvider`), so no key
  and no network — the grid path has zero LLM dependency.

Exit: `uv run --extra web uvicorn …` serves a generated mini as JSON, stores it, reads it
back; the full gate is green.

## Phase 2 — the playable loop (the product, and the instrument)

Make it *played*, and make playing *measured*.

- **Fold the `site/` player against the live API** instead of embedding JSON — the player
  already derives structure/numbering/navigation from puzzle data, so it is a fetch swap,
  not a rewrite. A "daily mini" served from `GET /puzzles/{id}`.
- **`POST /puzzles/{id}/solve`** — log a completed (or abandoned) solve: wall-clock solve
  time, per-entry check/reveal usage, and the final board. **This log is the deliverable** —
  it is the human solve-time signal every difficulty open-question is blocked on. It needs a
  place to live (the repository, extended, or a sibling `SolveLog` port) and it must store
  *what the solver did*, never leak the key (the same anti-corruption boundary `SolveView`
  draws on the agent side, D26).
- Keep it honest about privacy/scope: solve telemetry is data a human generated; log only
  what the calibration needs, and say so.

Exit: a person can open a URL, solve a real generated+clued puzzle, and the server has a
timed record of how it went.

## Phase 3 — close the cybernetics (where both streams finally meet)

The payoff the whole project was implicitly building toward.

- **Calibrate the difficulty model against human solve-times.** The logged times are the
  IRT `θ`/`b` ground truth D21/D22 named. `solve_order`'s `gimme` and the Mon–Sat clue enum
  stop being *uncalibrated* knobs and get fit to real data — the "needs human solve logs"
  blocker, lifted.
- **Validate the LLM-solver proxy (D26) against reality.** We can finally ask the question
  D26 could only bracket: does reasoning-token spend actually track *human* difficulty, or
  only *a* model's? Confirm, refute, or bound it — that is a real finding either way, and
  it is the D19/D28 measure-then-record discipline pointed at the solver.
- The **batch-difficulty scheduler** (D21 layer C) gets its missing input — a per-puzzle
  human-difficulty number to schedule a week's bell curve against, with the D31 denominator
  (38 distinct top-tier 5×5s) informing variety.

This is the "feedback loop up, loop off" in full: generation feeds the puzzle, the human
feeds the difficulty model, the difficulty model shapes the next puzzle.

## What this roadmap deliberately does not do

- It does **not** chase generation methods (WFC/ASP/15×15/template library). Those stay
  in `open-questions.md` as the *other* stream; they can resume once the product loop earns
  the attention, and the field/complete split (D27) means they compose rather than conflict.
- It does **not** add a database in Phase 1. In-memory first; the DB is a drop-in second
  adapter once the port and the loop are proven (the port is what makes it drop-in).
- It does **not** bundle "and also" work into a phase. Each phase is one PR-sized concern.

## Reversal

The direction is a scope call (D34), not an engine or invariant change, so it reverses by
*deprioritisation*, not by ripping code out — the API/persistence seams are additive and
sit at the `cli`/adapter edge. If the human-signal loop (Phase 2) turns out not to produce a
usable calibration signal (too few plays, too noisy), Phase 3's premise weakens and the
project can fall back to the LLM-proxy difficulty work or the generation stream — but Phases
1–2 (a served, playable, persisted puzzle) stand on their own as the product regardless.
