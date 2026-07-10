"""puzzledesk.bootstrap -- the composition root.

The only layer allowed to import everything: it wires concrete ``adapters`` into
``app`` services and hands back a :class:`~puzzledesk.bootstrap.container.Container`.
Entry points (``cli``) call :func:`build` and then just use the graph.
"""

from __future__ import annotations

from puzzledesk.bootstrap.build import build
from puzzledesk.bootstrap.config import Config
from puzzledesk.bootstrap.container import Container

__all__ = ["Config", "Container", "build"]
