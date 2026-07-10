"""The numpy randomness adapter -- the injected Prng.

``np.random.default_rng`` is confined to this one file. Everything else takes the
``Rng``/``RngFactory`` ports, so the impure dependency has exactly one binding
point and a test can swap in a recording or deterministic double.
"""

from __future__ import annotations

import numpy as np

from puzzledesk.core.rng import Rng


class NumpyRngFactory:
    """Implements ``core.rng.RngFactory`` over numpy. ``create(seed)`` returns a
    fresh ``np.random.default_rng(seed)`` -- a ``Generator`` that structurally *is*
    an :class:`~puzzledesk.core.rng.Rng`, so no wrapper is needed. Equal seeds give
    equal streams, which is what keeps the whole system reproducible."""

    def create(self, seed: int) -> Rng:
        return np.random.default_rng(seed)
