"""The composition root: build the container in explicit stages.

Wiring is the one place that is *allowed* to know every concrete type, so it is
the one place we keep it -- out of the engines, out of the services, out of the
CLIs. Reading top to bottom you see the whole object graph assemble in three
stages:

  1. **config**   -- resolve where to read data and where to write output;
  2. **adapters** -- construct the impure infrastructure (Prng, filesystem, stdout);
  3. **services** -- wire the pure application use-cases onto those adapters.

Each stage depends only on the ones before it, so the dependency direction is
obvious and a test can substitute at any layer (a different ``Config``, a fake
adapter set, or just call a service constructor directly).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from puzzledesk.adapters.claude_clue import ClaudeClueProvider
from puzzledesk.adapters.claude_solver import ClaudeSolverAgent
from puzzledesk.adapters.file_lexicon import FileLexicon
from puzzledesk.adapters.numpy_rng import NumpyRngFactory
from puzzledesk.adapters.writer import StreamWriter
from puzzledesk.app.blocked import BlockedGenerateService
from puzzledesk.app.clue import ClueProvider
from puzzledesk.app.cluing import ClueService
from puzzledesk.app.mini import MiniService
from puzzledesk.app.ports import LexiconSource, Writer
from puzzledesk.app.puzzle_service import PuzzleService
from puzzledesk.app.solve_service import SolveService
from puzzledesk.app.solver import SolverAgent
from puzzledesk.bootstrap.config import Config
from puzzledesk.bootstrap.container import Container
from puzzledesk.core.rng import RngFactory


@dataclass(frozen=True, slots=True)
class _Adapters:
    """Stage-2 output: the impure bindings, behind their port types."""

    rng_factory: RngFactory
    lexicon: LexiconSource
    writer: Writer
    clue_provider: ClueProvider
    solver_agent: SolverAgent


def _stage_config(config: Config | None) -> Config:
    return config if config is not None else Config.default()


def _resolve_api_key(env_name: str | None) -> str | None:
    """Read the clue API key from the configured env var -- the one place the
    composition root reaches into the environment for a secret, so adapters stay
    pure value-takers. A ``None`` name (or a name set to nothing) means "no key" ->
    the adapter defers to the SDK's own resolution. Reading here yields ``None``
    harmlessly when unset, so the container still builds without a key."""
    if not env_name:
        return None
    return os.environ.get(env_name) or None


def _stage_adapters(config: Config) -> _Adapters:
    # ClaudeClueProvider imports the `anthropic` SDK lazily, so constructing it (and
    # the whole container) needs neither the extra installed nor a key -- only an
    # actual clue call does. The key is resolved here and injected; the adapter itself
    # never touches the environment.
    return _Adapters(
        rng_factory=NumpyRngFactory(),
        lexicon=FileLexicon(config.data_dir),
        writer=StreamWriter(config.stream),
        clue_provider=ClaudeClueProvider(
            model=config.clue_model, api_key=_resolve_api_key(config.clue_api_key_env)
        ),
        # The second LLM adapter (D26): same key/env wiring as the clue provider, and
        # likewise imported lazily -- the container builds without the SDK or a key.
        solver_agent=ClaudeSolverAgent(
            model=config.solve_model,
            max_tokens=config.solve_max_tokens,
            thinking_mode=config.solve_thinking,
            effort=config.solve_effort,
            thinking_budget=config.solve_thinking_budget,
            api_key=_resolve_api_key(config.clue_api_key_env),
        ),
    )


def _stage_services(config: Config, adapters: _Adapters) -> Container:
    mini = MiniService(adapters.lexicon, adapters.rng_factory)
    blocked = BlockedGenerateService(adapters.lexicon, adapters.rng_factory)
    clue = ClueService(adapters.clue_provider)
    puzzle = PuzzleService(blocked, clue)
    solve = SolveService(adapters.solver_agent, max_turns=config.solve_max_turns)
    return Container(
        config=config,
        rng_factory=adapters.rng_factory,
        lexicon=adapters.lexicon,
        writer=adapters.writer,
        mini=mini,
        blocked=blocked,
        clue=clue,
        puzzle=puzzle,
        solve=solve,
    )


def build(config: Config | None = None) -> Container:
    """Assemble the container. Pass a ``Config`` to override defaults (e.g. a
    different data directory or output stream); otherwise sane defaults are used."""
    config = _stage_config(config)
    adapters = _stage_adapters(config)
    return _stage_services(config, adapters)
