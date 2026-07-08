"""The randomness port: numpy satisfies it, and injection is reproducible."""

from __future__ import annotations

import numpy as np

from puzzledesk.adapters.numpy_rng import NumpyRngFactory
from puzzledesk.core.rng import Rng, RngFactory


def test_numpy_generator_is_an_rng() -> None:
    # The whole design leans on a real Generator being an Rng with no wrapper.
    assert isinstance(np.random.default_rng(0), Rng)


def test_numpy_factory_is_an_rng_factory() -> None:
    assert isinstance(NumpyRngFactory(), RngFactory)


def test_factory_streams_are_reproducible_per_seed() -> None:
    f = NumpyRngFactory()
    a = f.create(7).integers(0, 1000, size=5)
    b = f.create(7).integers(0, 1000, size=5)
    assert list(a) == list(b)  # equal seed -> equal stream (the reproducibility invariant)


def test_different_seeds_diverge() -> None:
    f = NumpyRngFactory()
    a = f.create(1).integers(0, 1_000_000, size=5)
    b = f.create(2).integers(0, 1_000_000, size=5)
    assert list(a) != list(b)
