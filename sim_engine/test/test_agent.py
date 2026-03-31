"""Tests for sim_engine.agent — Pose, Velocity, Agent dataclasses."""

import math
import pytest

from sim_engine.agent import Agent, Pose, Velocity


class TestPose:
    def test_defaults(self):
        p = Pose()
        assert p.latitude == 0.0
        assert p.longitude == 0.0
        assert p.altitude == 0.0
        assert p.heading == 0.0
        assert p.pitch == 0.0
        assert p.roll == 0.0

    def test_distance_same_point(self):
        p = Pose(latitude=38.9, longitude=-77.0)
        assert p.distance_to(p) == 0.0

    def test_distance_equator_one_degree_lon(self):
        """One degree of longitude at the equator ~ 111 km."""
        p1 = Pose(latitude=0.0, longitude=0.0)
        p2 = Pose(latitude=0.0, longitude=1.0)
        dist = p1.distance_to(p2)
        assert 110_000 < dist < 112_000

    def test_distance_one_degree_lat(self):
        """One degree of latitude ~ 111 km everywhere."""
        p1 = Pose(latitude=0.0, longitude=0.0)
        p2 = Pose(latitude=1.0, longitude=0.0)
        dist = p1.distance_to(p2)
        assert 110_000 < dist < 112_000

    def test_distance_small_offset(self):
        """~0.001 deg lat ~ 111 meters."""
        p1 = Pose(latitude=38.9000, longitude=-77.0)
        p2 = Pose(latitude=38.9010, longitude=-77.0)
        dist = p1.distance_to(p2)
        assert 100 < dist < 120

    def test_distance_symmetric(self):
        p1 = Pose(latitude=10.0, longitude=20.0)
        p2 = Pose(latitude=11.0, longitude=21.0)
        assert abs(p1.distance_to(p2) - p2.distance_to(p1)) < 0.001

    def test_distance_3d_includes_altitude(self):
        p1 = Pose(latitude=0.0, longitude=0.0, altitude=0.0)
        p2 = Pose(latitude=0.0, longitude=0.0, altitude=100.0)
        assert p1.distance_3d_to(p2) == pytest.approx(100.0, abs=0.1)

    def test_distance_3d_pythagorean(self):
        """3D distance should be sqrt(horiz^2 + vert^2)."""
        p1 = Pose(latitude=0.0, longitude=0.0, altitude=0.0)
        p2 = Pose(latitude=0.0, longitude=0.0, altitude=300.0)
        horiz = p1.distance_to(p2)  # should be ~0
        d3d = p1.distance_3d_to(p2)
        assert d3d == pytest.approx(300.0, abs=1.0)


class TestVelocity:
    def test_defaults(self):
        v = Velocity()
        assert v.vx == 0.0
        assert v.vy == 0.0
        assert v.vz == 0.0
        assert v.wx == 0.0
        assert v.wy == 0.0
        assert v.wz == 0.0


class TestAgent:
    def test_defaults(self):
        a = Agent(agent_name="test")
        assert a.agent_name == "test"
        assert a.pose.latitude == 0.0
        assert a.velocity.vx == 0.0
        assert a.domain_id == 0
        assert a.vehicle_type == ""
        assert a.sensors == {}
        assert a.motion_model is None

    def test_with_data(self, agent_basic):
        assert agent_basic.agent_name == "uav_01"
        assert agent_basic.domain_id == 1
        assert agent_basic.vehicle_type == "uav"
        assert agent_basic.vehicle_class == "quadrotor"
        assert agent_basic.pose.altitude == 100.0
