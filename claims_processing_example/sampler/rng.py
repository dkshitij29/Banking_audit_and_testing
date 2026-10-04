"""Deterministic random draws from a seed, stable across Python versions.

Built only on random.Random seeded from a string (SHA-512 based, unchanged since
Python 3.2) and getrandbits(), whose output is the raw Mersenne Twister stream.
Choice, integer and sampling helpers are implemented here rather than borrowed
from the random module, whose implementations have changed between versions.
Same seed and streams, same draws, forever (CLAUDE.md invariant 4).
"""

from __future__ import annotations

import datetime as dt
import random
from collections.abc import Sequence


class Rng:
    def __init__(self, seed: int, *streams: str) -> None:
        self._key = ":".join(["claims-benchmark", str(seed), *streams])
        self._random = random.Random(self._key)
        self._seed = seed
        self._streams = streams

    def fork(self, *streams: str) -> Rng:
        """An independent stream, so extra draws in one part never shift another."""
        return Rng(self._seed, *self._streams, *streams)

    def below(self, n: int) -> int:
        """Uniform integer in [0, n)."""
        if n < 1:
            raise ValueError(f"below({n})")
        bits = n.bit_length()
        while True:
            value = self._random.getrandbits(bits)
            if value < n:
                return value

    def between(self, low: int, high: int) -> int:
        """Uniform integer in [low, high], both ends included."""
        return low + self.below(high - low + 1)

    def chance(self, percent: int) -> bool:
        return self.below(100) < percent

    def choice[T](self, items: Sequence[T]) -> T:
        return items[self.below(len(items))]

    def sample[T](self, items: Sequence[T], k: int) -> list[T]:
        """k distinct items, in draw order."""
        pool = list(items)
        picked = []
        for _ in range(min(k, len(pool))):
            picked.append(pool.pop(self.below(len(pool))))
        return picked

    def shuffled[T](self, items: Sequence[T]) -> list[T]:
        return self.sample(items, len(items))

    def date_between(self, first: dt.date, last: dt.date) -> dt.date:
        return first + dt.timedelta(days=self.below((last - first).days + 1))

    def rupees(self, low: int, high: int, step: int = 1) -> int:
        """A price in [low, high], a multiple of step."""
        return self.between(low // step, high // step) * step
