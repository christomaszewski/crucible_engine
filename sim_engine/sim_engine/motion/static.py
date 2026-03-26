"""Static motion model — agent remains at its initial pose."""

from __future__ import annotations

from typing import Any

from sim_engine.agent import Agent
from sim_engine.motion import MotionModel, register_motion
from sim_engine.world_state import WorldState


@register_motion("static")
class StaticMotionModel(MotionModel):
    """Agent does not move. Simplest motion model."""

    def configure(self, params: dict[str, Any]) -> None:
        pass

    def step(self, agent: Agent, world: WorldState, dt: float) -> None:
        pass
