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

from dataclasses import dataclass

from ..adapters.file_lexicon import FileLexicon
from ..adapters.numpy_rng import NumpyRngFactory
from ..adapters.writer import StreamWriter
from ..app.blocked import BlockedGenerateService
from ..app.mini import MiniService
from ..app.ports import LexiconSource, Writer
from ..core.rng import RngFactory
from .config import Config
from .container import Container


@dataclass(frozen=True, slots=True)
class _Adapters:
    """Stage-2 output: the impure bindings, behind their port types."""

    rng_factory: RngFactory
    lexicon: LexiconSource
    writer: Writer


def _stage_config(config: Config | None) -> Config:
    return config if config is not None else Config.default()


def _stage_adapters(config: Config) -> _Adapters:
    return _Adapters(
        rng_factory=NumpyRngFactory(),
        lexicon=FileLexicon(config.data_dir),
        writer=StreamWriter(config.stream),
    )


def _stage_services(config: Config, adapters: _Adapters) -> Container:
    mini = MiniService(adapters.lexicon, adapters.rng_factory)
    blocked = BlockedGenerateService(adapters.lexicon, adapters.rng_factory)
    return Container(
        config=config,
        rng_factory=adapters.rng_factory,
        lexicon=adapters.lexicon,
        writer=adapters.writer,
        mini=mini,
        blocked=blocked,
    )


def build(config: Config | None = None) -> Container:
    """Assemble the container. Pass a ``Config`` to override defaults (e.g. a
    different data directory or output stream); otherwise sane defaults are used."""
    config = _stage_config(config)
    adapters = _stage_adapters(config)
    return _stage_services(config, adapters)
