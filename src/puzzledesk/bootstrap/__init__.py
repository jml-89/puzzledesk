"""puzzledesk.bootstrap -- the composition root.

The only layer allowed to import everything: it wires concrete ``adapters`` into
``app`` services and hands back a :class:`~puzzledesk.bootstrap.container.Container`.
Entry points (``cli``) call :func:`build` and then just use the graph.
"""

from __future__ import annotations

from .build import build
from .config import Config
from .container import Container

__all__ = ["Config", "Container", "build"]
