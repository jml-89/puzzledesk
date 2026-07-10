"""The service container -- the assembled object graph.

A frozen record of everything the composition root resolved: the impure adapters
behind their port types, and the application services already wired to them. An
entry point takes a ``Container`` and reaches for what it needs (``c.mini``,
``c.writer``); nothing constructs its own dependencies past this point.

Fields are typed as *ports* where a port exists (``RngFactory``, ``LexiconSource``,
``Writer``) so the graph reads against interfaces, and as concrete services where
those are the application's own types.
"""

from __future__ import annotations

from dataclasses import dataclass

from puzzledesk.app.blocked import BlockedGenerateService
from puzzledesk.app.cluing import ClueService
from puzzledesk.app.mini import MiniService
from puzzledesk.app.ports import LexiconSource, Writer
from puzzledesk.app.puzzle_service import PuzzleService
from puzzledesk.app.solve_service import SolveService
from puzzledesk.bootstrap.config import Config
from puzzledesk.core.rng import RngFactory


@dataclass(frozen=True, slots=True)
class Container:
    config: Config
    rng_factory: RngFactory
    lexicon: LexiconSource
    writer: Writer
    mini: MiniService
    blocked: BlockedGenerateService
    clue: ClueService
    puzzle: PuzzleService
    solve: SolveService
