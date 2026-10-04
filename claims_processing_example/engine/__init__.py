"""Deterministic claim adjudication engine: the only code that decides gold answers."""

from engine.rules import ENGINE_VERSION, adjudicate
from engine.schema import UnsupportedCase

__all__ = ["ENGINE_VERSION", "UnsupportedCase", "adjudicate"]
