"""puzzledesk: dense crossword (double word square) generation.

Organised as a hexagon (ports & adapters), a linear import stack enforced by
import-linter (see ``[tool.importlinter]`` in ``pyproject.toml``):

    core  <  app  <  adapters  <  bootstrap  <  cli

  * ``core``      -- the pure kernel: grid models, engines, lexicon, acceptance
    test. No I/O, deterministic given a seed. Defines the one port it needs from
    outside (``core.rng.Rng`` -- randomness is injected, not constructed here).
  * ``app``       -- use-case services + the ports they need (``LexiconSource``,
    ``Writer``). Orchestrates the core; never touches a concrete adapter.
  * ``adapters``  -- infrastructure implementing the ports: numpy Prng, filesystem
    word lists, stdout. The one place effects are bound.
  * ``bootstrap`` -- the composition root: builds the service container in explicit
    stages (config -> adapters -> services).
  * ``cli``       -- thin entry points: argv -> build -> run -> present.

See ``docs/architecture.md`` for the data model and invariants, and
``docs/decisions.md`` D14 for why the code is shaped this way.
"""
