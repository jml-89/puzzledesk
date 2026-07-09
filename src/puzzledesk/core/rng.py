"""The randomness port: the kernel's one impure dependency, injected not built.

Every engine used to open its own ``np.random.default_rng(seed)``. That buried an
effect (randomness) inside otherwise-pure code and made "inject a recording or
fake stream under test" impossible. Here we name the two shapes the engines
actually need and depend only on those:

  * :class:`Rng` -- a single random stream. The engines call ``shuffle`` (candidate
    order for per-seed diversity); ``integers`` is the generic determinism probe the
    port test uses. ``numpy.random.Generator`` satisfies this structurally, so the
    default adapter is just ``np.random.default_rng(seed)`` with no wrapper.
  * :class:`RngFactory` -- makes a fresh stream from a seed. This is what preserves
    the reproducibility invariant: ``factory.create(seed)`` yields the identical
    stream every time, so a given ``(lists, seed)`` reproduces exactly, and a
    caller that re-seeds per attempt (``fill_by_count``) or loops over seeds (a
    service) gets independent, repeatable streams.

These are ``Protocol``s (structural), so nothing in the kernel imports numpy for
the *type* -- the concrete numpy adapter lives outside, in ``adapters``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Rng(Protocol):
    """One random stream. A subset of ``numpy.random.Generator``'s surface -- the
    operations the engines actually use -- so a real ``Generator`` is an ``Rng``
    as-is (structural match) and a test double only has to implement these two.

    Signatures use ``Any`` deliberately: the port abstracts a slice of numpy's
    dynamically-typed Generator (``shuffle`` mutates arrays *and* plain lists;
    ``integers`` returns numpy scalars or arrays depending on args), and pinning
    stricter types here would just fight the call sites. The kernel does not even
    import numpy for these -- the concrete adapter lives in ``adapters``.
    """

    def shuffle(self, x: Any) -> None:
        """Shuffle a sequence (numpy array or list) in place -- candidate order."""
        ...

    def integers(self, low: int, high: int | None = ..., size: int | None = ...) -> Any:
        """Random integers in ``[0, low)`` or ``[low, high)``."""
        ...


@runtime_checkable
class RngFactory(Protocol):
    """Makes a fresh :class:`Rng` from a seed. Injecting the *factory* (not a
    single stream) is what lets pure code stay reproducible: same seed in, same
    stream out, every call."""

    def create(self, seed: int) -> Rng:
        """A deterministic stream for ``seed`` (equal seeds give equal streams)."""
        ...
