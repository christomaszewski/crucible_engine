"""Tests for sim_engine.sensors — all built-in sensor models."""

import math
import pytest

from sim_engine.agent import Agent, Pose, Velocity
from sim_engine.sensors import SENSOR_REGISTRY, SensorModel
from sim_engine.sensors.navsatfix import NavSatFixModel
from sim_engine.sensors.imu import ImuModel, euler_to_quaternion
from sim_engine.sensors.altimeter import AltimeterModel
from sim_engine.sensors.twr_radio import TwrRadioModel
from sim_engine.world_state import WorldState


# -- Registry ------------------------------------------------------------------

class TestSensorRegistry:
    def test_builtin_sensors_registered(self):
        assert "navsatfix" in SENSOR_REGISTRY
        assert "imu" in SENSOR_REGISTRY
        assert "altimeter" in SENSOR_REGISTRY
        assert "twr_radio" in SENSOR_REGISTRY

    def test_registry_types(self):
        assert SENSOR_REGISTRY["navsatfix"] is NavSatFixModel
        assert SENSOR_REGISTRY["imu"] is ImuModel

    def test_instantiate_from_registry(self):
        sensor = SENSOR_REGISTRY["navsatfix"]()
        assert isinstance(sensor, SensorModel)


# -- Base SensorModel ----------------------------------------------------------

class TestSensorModelBase:
    def test_seeded_gauss_deterministic(self):
        s1 = NavSatFixModel()
        s1.set_seed(42)
        vals1 = [s1.gauss(0, 1) for _ in range(10)]

        s2 = NavSatFixModel()
        s2.set_seed(42)
        vals2 = [s2.gauss(0, 1) for _ in range(10)]

        assert vals1 == vals2

    def test_different_seeds_differ(self):
        s1 = NavSatFixModel()
        s1.set_seed(42)
        vals1 = [s1.gauss(0, 1) for _ in range(100)]

        s2 = NavSatFixModel()
        s2.set_seed(99)
        vals2 = [s2.gauss(0, 1) for _ in range(100)]

        assert vals1 != vals2

    def test_rate_limiting(self):
        s = NavSatFixModel()
        s.configure({"rate_hz": 10.0})  # 10 Hz = 0.1s period
        assert s.should_publish(0.05) is False  # 50ms < 100ms period
        assert s.should_publish(0.06) is True   # accumulated 110ms >= 100ms


# -- NavSatFix -----------------------------------------------------------------

class TestNavSatFix:
    def test_default_config(self):
        s = NavSatFixModel()
        cfg = s.get_config()
        assert cfg["type"] == "navsatfix"
        assert cfg["noise"]["horizontal_std_m"] == 1.5
        assert cfg["noise"]["vertical_std_m"] == 3.0

    def test_configure(self):
        s = NavSatFixModel()
        s.configure({
            "rate_hz": 5.0,
            "noise": {"horizontal_std_m": 2.0, "vertical_std_m": 5.0},
            "seed": 123,
        })
        assert s.rate_hz == 5.0
        cfg = s.get_config()
        assert cfg["noise"]["horizontal_std_m"] == 2.0

    def test_update_returns_message(self):
        s = NavSatFixModel()
        s.configure({"rate_hz": 1.0, "seed": 42})
        agent = Agent(
            agent_name="test",
            pose=Pose(latitude=38.9, longitude=-77.0, altitude=100.0),
        )
        world = WorldState()
        # First call with enough dt should publish
        msg = s.update(agent, world, 1.0)
        assert msg is not None
        # Check message has noisy but close-to-truth values
        assert abs(msg.latitude - 38.9) < 0.01
        assert abs(msg.longitude - (-77.0)) < 0.01

    def test_update_rate_limited(self):
        s = NavSatFixModel()
        s.configure({"rate_hz": 1.0})
        agent = Agent(agent_name="test", pose=Pose())
        world = WorldState()
        s.update(agent, world, 1.0)  # publishes
        msg = s.update(agent, world, 0.1)  # too soon
        assert msg is None

    def test_noise_statistics(self):
        """Verify noise has roughly correct standard deviation."""
        s = NavSatFixModel()
        s.configure({"rate_hz": 1000.0, "noise": {"horizontal_std_m": 2.0}, "seed": 42})
        agent = Agent(agent_name="test", pose=Pose(latitude=0.0, longitude=0.0))
        world = WorldState()

        lat_errors = []
        for _ in range(500):
            msg = s.update(agent, world, 0.001)
            if msg:
                # Convert lat error back to meters (1 deg lat ~ 111km)
                lat_errors.append((msg.latitude - 0.0) * 111_000)

        assert len(lat_errors) > 400
        import statistics
        std = statistics.stdev(lat_errors)
        # Should be roughly 2.0m (allow wide tolerance for sample size)
        assert 1.0 < std < 4.0


# -- IMU -----------------------------------------------------------------------

class TestImu:
    def test_default_config(self):
        s = ImuModel()
        cfg = s.get_config()
        assert cfg["type"] == "imu"
        assert cfg["noise"]["accel_std"] == 0.01

    def test_configure(self):
        s = ImuModel()
        s.configure({"rate_hz": 100.0, "noise": {"accel_std": 0.05}})
        assert s.rate_hz == 100.0

    def test_update_returns_message(self):
        s = ImuModel()
        s.configure({"rate_hz": 1.0, "seed": 42})
        agent = Agent(agent_name="test", pose=Pose(heading=0.5))
        world = WorldState()
        msg = s.update(agent, world, 1.0)
        assert msg is not None
        # Gravity should dominate z-acceleration
        assert abs(msg.linear_acceleration.z - ImuModel.GRAVITY) < 1.0

    def test_euler_to_quaternion_identity(self):
        """Zero Euler angles should give identity quaternion."""
        q = euler_to_quaternion(0.0, 0.0, 0.0)
        assert abs(q.w - 1.0) < 1e-6
        assert abs(q.x) < 1e-6
        assert abs(q.y) < 1e-6
        assert abs(q.z) < 1e-6

    def test_euler_to_quaternion_yaw_90(self):
        """90 deg yaw should have non-zero z component."""
        q = euler_to_quaternion(0.0, 0.0, math.pi / 2)
        assert abs(q.z) > 0.1


# -- Altimeter -----------------------------------------------------------------

class TestAltimeter:
    def test_default_config(self):
        s = AltimeterModel()
        cfg = s.get_config()
        assert cfg["type"] == "altimeter"
        assert cfg["noise"]["std_m"] == 0.5

    def test_update_msl_mode(self):
        s = AltimeterModel()
        s.configure({"rate_hz": 1.0, "use_agl": False, "seed": 42})
        agent = Agent(agent_name="test", pose=Pose(altitude=500.0))
        world = WorldState()
        msg = s.update(agent, world, 1.0)
        assert msg is not None
        assert abs(msg.data - 500.0) < 5.0  # noisy but close

    def test_update_agl_no_terrain(self):
        """AGL mode without terrain model falls back to MSL."""
        s = AltimeterModel()
        s.configure({"rate_hz": 1.0, "use_agl": True, "seed": 42})
        agent = Agent(agent_name="test", pose=Pose(altitude=200.0))
        world = WorldState()  # no terrain
        msg = s.update(agent, world, 1.0)
        assert msg is not None
        assert abs(msg.data - 200.0) < 5.0


# -- TWR Radio -----------------------------------------------------------------

class TestTwrRadio:
    def test_default_config(self):
        s = TwrRadioModel()
        cfg = s.get_config()
        assert cfg["type"] == "twr_radio"
        assert cfg["max_range_m"] == 500.0

    def test_configure(self):
        s = TwrRadioModel()
        s.configure({"max_range_m": 1000.0, "noise": {"std_m": 0.5}})
        cfg = s.get_config()
        assert cfg["max_range_m"] == 1000.0
        assert cfg["noise"]["std_m"] == 0.5

    def test_update_with_neighbors(self):
        """Two agents ~111m apart, both with twr_radio — should get range."""
        world = WorldState()
        a1 = Agent(agent_name="uav_01", pose=Pose(latitude=38.9072, longitude=-77.0369))
        a2 = Agent(agent_name="uav_02", pose=Pose(latitude=38.9082, longitude=-77.0369))
        # Both agents need twr_radio sensors for sensor_type filtering
        r1, r2 = TwrRadioModel(), TwrRadioModel()
        a1.sensors["twr_radio"] = r1
        a2.sensors["twr_radio"] = r2
        world.add_agent(a1)
        world.add_agent(a2)

        s = TwrRadioModel()
        s.configure({"rate_hz": 1.0, "max_range_m": 500.0, "seed": 42})
        msg = s.update(a1, world, 1.0)
        assert msg is not None
        assert len(msg.ranges) == 1
        assert 100 < msg.ranges[0].range_m < 130  # ~111m with noise

    def test_update_out_of_range(self):
        """Set max range below actual distance — returns None (no neighbors)."""
        world = WorldState()
        a1 = Agent(agent_name="uav_01", pose=Pose(latitude=38.9072, longitude=-77.0369))
        a2 = Agent(agent_name="uav_02", pose=Pose(latitude=38.9082, longitude=-77.0369))
        a1.sensors["twr_radio"] = TwrRadioModel()
        a2.sensors["twr_radio"] = TwrRadioModel()
        world.add_agent(a1)
        world.add_agent(a2)

        s = TwrRadioModel()
        s.configure({"rate_hz": 1.0, "max_range_m": 10.0, "seed": 42})
        msg = s.update(a1, world, 1.0)
        # No neighbors within 10m, so returns None
        assert msg is None

    def test_update_no_neighbors(self):
        """Single agent — returns None (no neighbors)."""
        s = TwrRadioModel()
        s.configure({"rate_hz": 1.0, "seed": 42})
        world = WorldState()
        agent = Agent(agent_name="solo", pose=Pose())
        agent.sensors["twr_radio"] = TwrRadioModel()
        world.add_agent(agent)
        msg = s.update(agent, world, 1.0)
        assert msg is None
