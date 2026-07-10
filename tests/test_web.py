"""The HTTP API: POST /puzzles (generate + store) and GET /puzzles/{id} (read back).

Guarded by ``importorskip("fastapi")`` so the base gate (``uv run pytest``, no extra)
skips it and ``uv run --extra web pytest`` runs it -- the same isolation the ``web``
extra draws around FastAPI.

Wired against a real container with the clue provider swapped for the deterministic
``FakeClueProvider`` (``dataclasses.replace`` on the frozen container), so the grid is
filled from the committed ``cw`` data by the real engine -- a genuine end-to-end check --
with no model and no key. The completeness epistemics are asserted at the boundary: a
complete strategy's empty result is a 422 ``unsat`` (a proof), not a bland not-found.
"""

from __future__ import annotations

import dataclasses

import pytest

pytest.importorskip("fastapi")

from fakes import FakeClueProvider, InMemoryLexiconSource, RecordingRngFactory
from fastapi.testclient import TestClient

from puzzledesk.app.cluing import ClueService
from puzzledesk.app.generate import GenerateService
from puzzledesk.app.puzzle_service import PuzzleService
from puzzledesk.app.spec import CappedLayout
from puzzledesk.bootstrap import build
from puzzledesk.core.lexicon import Lexicon, MultiLexicon
from puzzledesk.web.app import create_app
from puzzledesk.web.schema import PuzzleRequest

# one word can never fill four distinct slots -> the complete fill search returns None
# (a UNSAT theorem, not a timeout), as in test_puzzle_service.
_UNFILLABLE = MultiLexicon({2: Lexicon(["ab"])})


def _client() -> TestClient:
    # Real container (real FileLexicon + engine + in-memory repo), fake clues.
    base = build()
    clue = ClueService(FakeClueProvider())
    container = dataclasses.replace(base, clue=clue, puzzle=PuzzleService(base.generator, clue))
    return TestClient(create_app(container))


def _fake_client(multi: MultiLexicon) -> TestClient:
    # A container whose generator draws from an in-memory lexicon, so a test can force a
    # deterministic complete-UNSAT (an unfillable list) rather than depend on the real data.
    base = build()
    gen = GenerateService(InMemoryLexiconSource(multi=multi), RecordingRngFactory())
    clue = ClueService(FakeClueProvider())
    container = dataclasses.replace(base, generator=gen, clue=clue, puzzle=PuzzleService(gen, clue))
    return TestClient(create_app(container))


def test_post_then_get_round_trip() -> None:
    client = _client()
    resp = client.post(
        "/puzzles",
        json={"grid": {"rows": 5, "cols": 5, "min_score": 90}, "layout": {"kind": "full_square"}},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["rows"] == 5 and body["cols"] == 5
    # a 5x5 double word square: five acrosses, five downs, all clued by the fake provider
    assert len(body["across"]) == 5 and len(body["down"]) == 5
    assert all(e["clue"] for e in body["across"]) and all(e["clue"] for e in body["down"])
    assert body["unclued"] == []

    got = client.get(f"/puzzles/{body['id']}")
    assert got.status_code == 200
    assert got.json() == body  # read-back is byte-identical to what POST returned


def test_unknown_id_is_404() -> None:
    assert _client().get("/puzzles/does-not-exist").status_code == 404


def test_unsat_from_a_complete_strategy_is_a_proof() -> None:
    # A 2x2 count layout over a one-word list has no distinct fill, so the complete
    # search returns None -- which must surface as a 422 "unsat" (a proof), not a
    # swallowed timeout and not a bland not-found.
    resp = _fake_client(_UNFILLABLE).post(
        "/puzzles",
        json={
            "grid": {"rows": 2, "cols": 2, "min_score": 0},
            "layout": {"kind": "count", "num_black": 0, "min_len": 2},
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason"] == "unsat"


def test_wire_schema_parses_a_discriminated_layout_into_the_spec() -> None:
    # the capped body carries only its own knobs and parses into a CappedLayout.
    req = PuzzleRequest.model_validate(
        {"grid": {"rows": 10, "cols": 10}, "layout": {"kind": "capped", "max_len": 5}}
    )
    spec = req.to_spec()
    assert isinstance(spec.layout, CappedLayout)
    assert spec.layout.max_len == 5
    assert spec.grid.rows == 10
