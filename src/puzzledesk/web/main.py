"""The production ASGI instance: ``uv run --extra web uvicorn puzzledesk.web.main:app``.

Assembles the real container (:func:`puzzledesk.bootstrap.build`) once at import and
hands it to :func:`~puzzledesk.web.app.create_app`. The clue stage still needs the
``clue`` extra + a key to produce real clues; the grid search does not, so a request for
an unclued/fake-clued puzzle works without either (the ``unclued`` list stays honest).
"""

from __future__ import annotations

from puzzledesk.bootstrap import build
from puzzledesk.web.app import create_app

app = create_app(build())
