"""Terrain elevation model backed by GeoTIFF DEM data."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class TerrainModel:
    """Provides terrain elevation lookups from a DEM raster file.

    Uses rasterio for efficient point queries against SRTM/DTED GeoTIFF data.
    Falls back gracefully if rasterio is not installed or the file is missing.
    """

    def __init__(self, dem_path: str) -> None:
        self._dataset = None
        self._band = None
        path = Path(dem_path)

        if not path.exists():
            logger.warning("DEM file not found: %s — terrain disabled", dem_path)
            return

        try:
            import rasterio  # noqa: F811

            self._dataset = rasterio.open(str(path))
            self._band = self._dataset.read(1)
            logger.info(
                "Terrain loaded: %s (%dx%d)",
                dem_path,
                self._band.shape[1],
                self._band.shape[0],
            )
        except ImportError:
            logger.warning("rasterio not installed — terrain disabled")
        except Exception:
            logger.exception("Failed to load DEM: %s", dem_path)

    @property
    def available(self) -> bool:
        return self._band is not None

    def get_elevation(self, lat: float, lon: float) -> float:
        """Return terrain elevation (meters above ellipsoid) at the given position.

        Returns 0.0 if terrain data is not available or the point is outside
        the DEM extent.
        """
        if self._dataset is None or self._band is None:
            return 0.0

        try:
            row, col = self._dataset.index(lon, lat)
            if 0 <= row < self._band.shape[0] and 0 <= col < self._band.shape[1]:
                return float(self._band[row, col])
        except Exception:
            pass

        return 0.0

    def close(self) -> None:
        if self._dataset is not None:
            self._dataset.close()
