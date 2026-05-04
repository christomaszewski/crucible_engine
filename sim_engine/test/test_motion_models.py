"""Tests for sim_engine.motion — all built-in motion models."""

import math
import pytest

from sim_engine.agent import Agent, Pose, Velocity
from sim_engine.motion import MOTION_REGISTRY, MotionModel
from sim_engine.motion.static import StaticMotionModel
from sim_engine.motion.waypoint import WaypointMotionModel
from sim_engine.motion.commanded import CommandedVelocityModel
from sim_engine.motion.log_playback import LogPlaybackMotionModel
from sim_engine.world_state import WorldState


# -- Registry ------------------------------------------------------------------

class TestMotionRegistry:
    def test_builtin_motions_registered(self):
        assert "static" in MOTION_REGISTRY
        assert "waypoint" in MOTION_REGISTRY
        assert "commanded_velocity" in MOTION_REGISTRY
        assert "log_playback" in MOTION_REGISTRY

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


# -- Log Playback --------------------------------------------------------------

class TestLogPlaybackMotion:
    def test_configure_defaults(self):
        m = LogPlaybackMotionModel()
        m.configure({})
        assert m.position_topic == "gps/fix"
        assert m.orientation_topic is None
        cfg = m.get_config()
        assert cfg["type"] == "log_playback"
        assert cfg["position_topic"] == "gps/fix"
        assert "orientation_topic" not in cfg

    def test_configure_explicit(self):
        m = LogPlaybackMotionModel()
        m.configure({"position_topic": "nav/fix", "orientation_topic": "imu"})
        assert m.position_topic == "nav/fix"
        assert m.orientation_topic == "imu"
        cfg = m.get_config()
        assert cfg["orientation_topic"] == "imu"

    def test_resolve_topic_relative(self):
        m = LogPlaybackMotionModel()
        m.configure({})
        assert m.resolve_topic("uav_01", "gps/fix") == "/uav_01/gps/fix"

    def test_resolve_topic_absolute(self):
        m = LogPlaybackMotionModel()
        m.configure({})
        assert m.resolve_topic("uav_01", "/global/topic") == "/global/topic"

    def test_step_no_messages_no_change(self):
        """Without any incoming messages, agent stays put."""
        m = LogPlaybackMotionModel()
        m.configure({})
        agent = Agent(agent_name="t", pose=Pose(latitude=10.0, longitude=20.0, altitude=50.0))
        world = WorldState()
        m.step(agent, world, 0.1)
        assert agent.pose.latitude == 10.0
        assert agent.pose.longitude == 20.0
        assert agent.pose.altitude == 50.0

    def test_position_message_updates_pose(self):
        from sensor_msgs.msg import NavSatFix
        m = LogPlaybackMotionModel()
        m.configure({})
        agent = Agent(agent_name="t", pose=Pose(latitude=0.0, longitude=0.0, altitude=0.0))
        world = WorldState()

        msg = NavSatFix()
        msg.latitude = 38.9072
        msg.longitude = -77.0369
        msg.altitude = 100.0
        m.on_position(msg)

        m.step(agent, world, 0.1)
        assert agent.pose.latitude == pytest.approx(38.9072)
        assert agent.pose.longitude == pytest.approx(-77.0369)
        assert agent.pose.altitude == pytest.approx(100.0)

    def test_velocity_estimated_between_positions(self):
        """Two successive positions should yield a non-zero velocity estimate."""
        from sensor_msgs.msg import NavSatFix
        m = LogPlaybackMotionModel()
        m.configure({})
        agent = Agent(agent_name="t", pose=Pose(latitude=0.0, longitude=0.0))
        world = WorldState()

        msg1 = NavSatFix()
        msg1.latitude = 0.0
        msg1.longitude = 0.0
        msg1.altitude = 0.0
        m.on_position(msg1)
        m.step(agent, world, 0.1)
        # First position seeds prev — velocity should still be zero
        assert agent.velocity.vx == 0.0
        assert agent.velocity.vy == 0.0

        msg2 = NavSatFix()
        msg2.latitude = 0.001  # ~111 m north
        msg2.longitude = 0.0
        msg2.altitude = 0.0
        m.on_position(msg2)
        m.step(agent, world, 1.0)
        # Roughly 111 m north over 1s → vx ~ 111
        assert agent.velocity.vx == pytest.approx(111.32, abs=1.0)
        assert abs(agent.velocity.vy) < 0.01

    def test_orientation_message_updates_heading(self):
        from sensor_msgs.msg import Imu
        from sim_engine.sensors.imu import euler_to_quaternion
        m = LogPlaybackMotionModel()
        m.configure({"orientation_topic": "imu/data"})
        agent = Agent(agent_name="t", pose=Pose())
        world = WorldState()

        msg = Imu()
        msg.orientation = euler_to_quaternion(0.0, 0.0, math.pi / 2.0)
        m.on_orientation(msg)
        m.step(agent, world, 0.1)
        assert agent.pose.heading == pytest.approx(math.pi / 2.0)

    def test_step_without_new_msg_keeps_pose(self):
        """After a position is applied, subsequent steps without new msgs keep pose."""
        from sensor_msgs.msg import NavSatFix
        m = LogPlaybackMotionModel()
        m.configure({})
        agent = Agent(agent_name="t", pose=Pose())
        world = WorldState()

        msg = NavSatFix()
        msg.latitude = 5.0
        msg.longitude = 6.0
        msg.altitude = 7.0
        m.on_position(msg)
        m.step(agent, world, 0.1)
        # Subsequent step with no new msg — pose unchanged
        m.step(agent, world, 0.1)
        assert agent.pose.latitude == pytest.approx(5.0)
        assert agent.pose.longitude == pytest.approx(6.0)
        assert agent.pose.altitude == pytest.approx(7.0)
