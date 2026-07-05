"""Adapter registry: maps adapter names to classes."""

from __future__ import annotations

from .base import BaseAdapter


def get_adapter(name: str) -> BaseAdapter:
    """Instantiate an adapter by name. Import lazily so a missing
    game-specific dependency never breaks the others."""
    if name == "sim":
        from .sim import SimAdapter
        return SimAdapter()
    if name == "lmu":
        from .lmu.adapter import LMUAdapter
        return LMUAdapter()
    raise ValueError(f"Unknown adapter '{name}'. Available: sim, lmu")
