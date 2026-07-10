"""puzzledesk.web -- the HTTP entry point (FastAPI), a top layer beside ``cli``.

The same shape as a ``cli`` entry (input -> ``build()`` -> run a service -> present),
with HTTP as the transport instead of argv. It is fenced behind a ``web`` optional
extra (FastAPI + uvicorn), isolated exactly like ``anthropic`` behind ``clue``: the
package and the whole gate run *without* it installed -- only importing
:mod:`puzzledesk.web.app` / :mod:`puzzledesk.web.schema` (or actually serving) pulls
FastAPI/Pydantic. So this ``__init__`` imports nothing heavy; reach for the submodules.

The wire schema (:mod:`puzzledesk.web.schema`) is a *separate* object that parses into
the canonical :class:`~puzzledesk.app.spec.PuzzleSpec` -- never *is* it (D15: the port
speaks the canonical form; serialization is an export concern). See D34 / docs/roadmap.md.
"""

from __future__ import annotations
