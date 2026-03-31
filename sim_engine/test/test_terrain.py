"""Tests for sim_engine.terrain — elevation model."""

import pytest

from sim_engine.terrain import TerrainModel


class TestTerrainModel:
    def test_nonexistent_file(self):
        """Should gracefully handle missing DEM files."""
        t = TerrainModel("/nonexistent/path/dem.tif")
        assert t.available is False

    def test_elevation_unavailable(self):
        """Without a valid DEM, should return 0.0."""
        t = TerrainModel("/nonexistent/path/dem.tif")
        assert t.get_elevation(38.9, -77.0) == 0.0

    def test_close_no_crash(self):
        """Closing without a loaded DEM should not raise."""
        t = TerrainModel("/nonexistent/path/dem.tif")
        t.close()
