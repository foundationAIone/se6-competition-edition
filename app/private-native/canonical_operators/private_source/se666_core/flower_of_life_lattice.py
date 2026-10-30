"""Flower of Life lattice mapping.

Deterministically arranges aspects of a task into nested rings:
  center, first_ring, second_ring, third_ring, outer_ring.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LatticeMap(BaseModel):
    center: str = Field(..., description="Core intention.")
    first_ring: list[str] = Field(default_factory=list)
    second_ring: list[str] = Field(default_factory=list)
    third_ring: list[str] = Field(default_factory=list)
    outer_ring: list[str] = Field(default_factory=list)


def _tokens(task: str) -> list[str]:
    return [t for t in task.replace(",", " ").split() if t]


def map_lattice(task: str) -> LatticeMap:
    """Map a task string into a Flower of Life lattice.

    Layout (deterministic, structural — not semantic AI):
      center      : compact intention summary
      first_ring  : direct subject/verb tokens (up to 6)
      second_ring : qualifiers and constraints (up to 12)
      third_ring  : domain context / nouns of scope
      outer_ring  : long-range concerns (ethics, future, repair)
    """
    text = task.strip()
    tokens = _tokens(text)

    center = (text[:80] + "…") if len(text) > 80 else text or "(empty)"

    first_ring = tokens[:6]
    second_ring = tokens[6:18]
    third_ring = tokens[18:36]

    outer_ring: list[str] = [
        "future_benefit",
        "responsibility",
        "coherence",
        "repair",
        "consent",
    ]

    return LatticeMap(
        center=center,
        first_ring=first_ring,
        second_ring=second_ring,
        third_ring=third_ring,
        outer_ring=outer_ring,
    )
