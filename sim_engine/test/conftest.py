"""Shared fixtures for sim_engine tests."""

import pytest

from sim_engine.agent import Agent, Pose, Velocity
from sim_engine.world_state import WorldState
from sim_engine.plugin_discovery import discover_all_plugins


@pytest.fixture(autouse=True, scope="session")
def _register_plugins():
    """Ensure all built-in sensor and motion plugins are registered."""
    discover_all_plugins()


@pytest.fixture
def pose_origin():
    return Pose(latitude=0.0, longitude=0.0, altitude=0.0, heading=0.0)


@pytest.fixture
def pose_dc():
    """Washington DC area pose."""
    return Pose(latitude=38.9072, longitude=-77.0369, altitude=100.0, heading=0.5)


@pytest.fixture
def agent_basic():
    return Agent(
        agent_name="uav_01",
        pose=Pose(latitude=38.9072, longitude=-77.0369, altitude=100.0),
        domain_id=1,
        vehicle_type="uav",
        vehicle_class="quadrotor",
    )


@pytest.fixture
def agent_second():
    return Agent(
        agent_name="uav_02",
        pose=Pose(latitude=38.9082, longitude=-77.0369, altitude=100.0),
        domain_id=2,
        vehicle_type="uav",
    )


@pytest.fixture
def world():
    return WorldState()


@pytest.fixture
def populated_world(world, agent_basic, agent_second):
    """WorldState with two agents ~111m apart (lat differs by ~0.001 deg)."""
    world.add_agent(agent_basic)
    world.add_agent(agent_second)
    return world
