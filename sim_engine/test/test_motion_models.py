"""Tests for sim_engine.motion — all built-in motion models."""

import math
import pytest

from sim_engine.agent import Agent, Pose, Velocity
from sim_engine.motion import MOTION_REGISTRY, MotionModel
from sim_engine.motion.static import StaticMotionModel
from sim_engine.motion.waypoint import WaypointMotionModel
from sim_engine.motion.commanded import CommandedVelocityModel
from sim_engine.world_state import WorldState


# -- Registry ------------------------------------------------------------------

class TestMotionRegistry:
    def test_builtin_motions_registered(self):
        assert "static" in MOTION_REGISTRY
        assert "waypoint" in MOTION_REGISTRY
        assert "commanded_velocity" in MOTION_REGISTRY

    def test_registry_types(self):
        assert MOTION_REGISTRY["static"] is StaticMotionModel

    def test_instantiate_from_registry(self):
        m = MOTION_REGISTRY["waypoint"]()
        assert isinstance(m, MotionModel)


# -- Static --------------------------------------------------------------------

class TestStaticMotion:
    def test_step_no_change(self):
        m = StaticMotionModel()
        m.configure({})
        agent = Agent(agent_name="test", pose=Pose(latitude=10.0, longitude=20.0, altitude=50.0))
        world = WorldState()
        m.step(agent, world, 1.0)
        assert agent.pose.latitude == 10.0
        assert agent.pose.longitude == 20.0
        assert agent.pose.altitude == 50.0


# -- Waypoint ------------------------------------------------------------------

class TestWaypointMotion:
    @pytest.fixture
    def waypoint_model(self):
        m = WaypointMotionModel()
        m.configure({
            "speed_mps": 10.0,
            "arrival_threshold_m": 5.0,
            "loop": False,
            "waypoints": [
                {"lat": 0.001, "lon": 0.0, "alt": 100.0},
                {"lat": 0.002, "lon": 0.0, "alt": 100.0},
            ],
        })
        return m

    def test_configure(self, waypoint_model):
        cfg = waypoint_model.get_config()
        assert cfg["type"] == "waypoint"
        assert cfg["speed_mps"] == 10.0
        assert len(cfg["waypoints"]) == 2

    def test_step_moves_toward_target(self, waypoint_model):
        agent = Agent(agent_name="test", pose=Pose(latitude=0.0, longitude=0.0, altitude=100.0))
        world = WorldState()
        old_lat = agent.pose.latitude
        waypoint_model.step(agent, world, 1.0)
        # Should move northward (increasing latitude)
        assert agent.pose.latitude > old_lat

    def test_step_updates_heading(self, waypoint_model):
        agent = Agent(agent_name="test", pose=Pose(latitude=0.0, longitude=0.0))
        world = WorldState()
        waypoint_model.step(agent, world, 1.0)
        # Heading toward lat=0.001, lon=0 should be roughly north (0 rad)
        assert abs(agent.pose.heading) < 0.1

    def test_arrival_advances_waypoint(self):
        """When close to waypoint, should advance to next."""
        m = WaypointMotionModel()
        m.configure({
            "speed_mps": 100.0,
            "arrival_threshold_m": 500.0,  # generous threshold
            "waypoints": [
                {"lat": 0.0001, "lon": 0.0, "alt": 0.0},  # very close
                {"lat": 1.0, "lon": 0.0, "alt": 0.0},      # far
            ],
        })
        agent = Agent(agent_name="test", pose=Pose(latitude=0.0, longitude=0.0))
        world = WorldState()
        # Step multiple times to reach first waypoint
        for _ in range(5):
            m.step(agent, world, 1.0)
        # Should have advanced past first waypoint index
        assert m._current_idx >= 1

    def test_no_waypoints_no_movement(self):
        m = WaypointMotionModel()
        m.configure({"waypoints": []})
        agent = Agent(agent_name="test", pose=Pose(latitude=5.0, longitude=10.0))
        world = WorldState()
        m.step(agent, world, 1.0)
        assert agent.pose.latitude == 5.0

    def test_loop_wraps_around(self):
        m = WaypointMotionModel()
        m.configure({
            "speed_mps": 1000.0,
            "arrival_threshold_m": 50000.0,  # always "arrived"
            "loop": True,
            "waypoints": [
                {"lat": 0.001, "lon": 0.0, "alt": 0.0},
                {"lat": 0.002, "lon": 0.0, "alt": 0.0},
            ],
        })
        agent = Agent(agent_name="test", pose=Pose())
        world = WorldState()
        # Step enough to cycle
        for _ in range(10):
            m.step(agent, world, 1.0)
        # With loop=True, index should wrap (not exceed len)
        assert m._current_idx < 2


# -- Commanded Velocity --------------------------------------------------------

class TestCommandedVelocity:
    def test_configure(self):
        m = CommandedVelocityModel()
        m.configure({"max_speed_mps": 30.0, "topic_suffix": "cmd_vel"})
        cfg = m.get_config()
        assert cfg["max_speed_mps"] == 30.0

    def test_step_no_command(self):
        """Without any command, agent should not move."""
        m = CommandedVelocityModel()
        m.configure({})
        agent = Agent(agent_name="test", pose=Pose(latitude=10.0, longitude=20.0))
        world = WorldState()
        m.step(agent, world, 1.0)
        assert agent.pose.latitude == 10.0
        assert agent.pose.longitude == 20.0

    def test_step_with_forward_command(self):
        """Forward velocity should change position."""
        from geometry_msgs.msg import Twist, Vector3
        m = CommandedVelocityModel()
        m.configure({"max_speed_mps": 50.0})
        cmd = Twist()
        cmd.linear.x = 10.0  # 10 m/s forward
        m.on_command(cmd)

        agent = Agent(
            agent_name="test",
            pose=Pose(latitude=0.0, longitude=0.0, heading=0.0),  # facing north
        )
        world = WorldState()
        old_lat = agent.pose.latitude
        m.step(agent, world, 1.0)
        # Moving north should increase latitude
        assert agent.pose.latitude > old_lat

    def test_max_speed_clamping(self):
        """Speed beyond max should be clamped."""
        from geometry_msgs.msg import Twist
        m = CommandedVelocityModel()
        m.configure({"max_speed_mps": 5.0})
        cmd = Twist()
        cmd.linear.x = 100.0  # way over limit
        m.on_command(cmd)

        agent = Agent(agent_name="test", pose=Pose(latitude=0.0, longitude=0.0, heading=0.0))
        world = WorldState()
        m.step(agent, world, 1.0)

        # With max 5 m/s and 1s dt, should move ~5m north
        # 5m of latitude ~ 5/111000 degrees ~ 0.000045 deg
        delta_lat = agent.pose.latitude
        assert delta_lat < 0.0001  # less than what 100 m/s would give

    def test_topic_suffix_property(self):
        m = CommandedVelocityModel()
        m.configure({"topic_suffix": "velocity_cmd"})
        assert m.topic_suffix == "velocity_cmd"
