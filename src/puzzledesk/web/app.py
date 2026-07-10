"""The FastAPI application: ``POST /puzzles`` (generate + store) and
``GET /puzzles/{id}`` (read back).

An entry point, so it takes an assembled :class:`~puzzledesk.bootstrap.container.Container`
and reaches for what it needs (``container.puzzle``, ``container.repository``) -- it
constructs no dependency of its own, exactly like a ``cli`` module. :func:`create_app`
is a factory (not a module-level singleton) so a test can hand it a container wired with
fakes; :mod:`puzzledesk.web.main` is the production instance uvicorn serves.

The completeness epistemics survive the HTTP boundary. When generation returns ``None``
the response is worded from the spec's layout tag
(:func:`~puzzledesk.app.spec.layout_is_complete`): a *complete* strategy's ``None`` is a
**UNSAT proof** (there is provably no such puzzle), a budgeted/sampled one's is mere
**budget exhaustion** -- never both collapsed into a bland "not found".
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from puzzledesk.app.spec import layout_is_complete
from puzzledesk.bootstrap.container import Container
from puzzledesk.web.schema import PuzzleRequest, PuzzleView, puzzle_view


def create_app(container: Container) -> FastAPI:
    """Build the FastAPI app over an assembled container."""
    app = FastAPI(
        title="puzzledesk",
        version="0.1.0",
        summary="Generate a clued crossword and read it back.",
    )

    @app.post("/puzzles", response_model=PuzzleView, status_code=201)
    def create_puzzle(request: PuzzleRequest) -> PuzzleView:
        spec = request.to_spec()
        puzzle = container.puzzle.generate(spec)
        if puzzle is None:
            complete = layout_is_complete(spec.layout)
            # A complete search that returns nothing has *proved* there is no puzzle;
            # a budgeted/sampled one has only run out of budget. Word it honestly.
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "unsat" if complete else "budget",
                    "message": (
                        "no acceptable puzzle exists for this request (a complete search "
                        "exhausted the space -- a UNSAT proof, not a timeout)"
                        if complete
                        else "no puzzle found within the search budget (a budget/sampler "
                        "limit, not a proof that none exists)"
                    ),
                },
            )
        pid = container.repository.save(spec, puzzle)
        stored = container.repository.get(pid)
        assert stored is not None  # just saved under this id
        return puzzle_view(stored)

    @app.get("/puzzles/{puzzle_id}", response_model=PuzzleView)
    def read_puzzle(puzzle_id: str) -> PuzzleView:
        stored = container.repository.get(puzzle_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="no such puzzle")
        return puzzle_view(stored)

    return app
