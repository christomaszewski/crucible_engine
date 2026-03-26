"""Motion model base class and plugin registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sim_engine.agent import Agent
    from sim_engine.world_state import WorldState

# ---------------------------------------------------------------------------
# Plugin registry
# ---------------------------------------------------------------------------

MOTION_REGISTRY: dict[str, type[MotionModel]] = {}


def register_motion(name: str):
    """Decorator to register a motion model class."""

    def decorator(cls: type[MotionModel]) -> type[MotionModel]:
        if name in MOTION_REGISTRY:
            raise ValueError(f"Motion model '{name}' already registered")
        MOTION_REGISTRY[name] = cls
        cls.motion_type_name = name
        return cls

    return decorator


def discover_motion_plugins() -> None:
    """Discover and load motion model plugins via entry points."""
    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="sim_engine.motion")
        for ep in eps:
            cls = ep.load()
            if ep.name not in MOTION_REGISTRY:
                MOTION_REGISTRY[ep.name] = cls
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Motion model ABC
# ---------------------------------------------------------------------------


class MotionModel(ABC):
    """Abstract base for agent motion models."""

    motion_type_name: str = ""

    @abstractmethod
    def configure(self, params: dict[str, Any]) -> None:
        """Load motion parameters from config dict."""
        ...

    @abstractmethod
    def step(self, agent: Agent, world: WorldState, dt: float) -> None:
        """Update agent pose and velocity in place for one time step."""
        ...

    def get_config(self) -> dict[str, Any]:
        """Return current config as a serializable dict."""
        return {"type": self.motion_type_name}
