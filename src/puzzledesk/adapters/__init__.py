"""puzzledesk.adapters -- infrastructure: concrete implementations of the ports.

The "back" of the hexagon. Each adapter binds one impure capability to a port the
core or app defined:

  * :class:`~puzzledesk.adapters.numpy_rng.NumpyRngFactory` -> ``core.rng.RngFactory``
    (the injected Prng: ``np.random.default_rng`` lives here, nowhere else);
  * :class:`~puzzledesk.adapters.file_lexicon.FileLexicon` -> ``app.ports.LexiconSource``
    (the filesystem read that used to sit in the kernel);
  * :class:`~puzzledesk.adapters.writer.StreamWriter` -> ``app.ports.Writer``
    (stdout in production; tests supply their own recording ``Writer``).

Adapters sit *above* ``app`` in the import graph (they import the ports they
implement) and *below* the composition root. import-linter forbids ``app`` from
importing back down into ``adapters`` -- that inversion is the whole point.
"""
