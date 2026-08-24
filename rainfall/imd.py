"""Access IMD (India Meteorological Department) gridded daily rainfall.

Source: IMD Pune 0.25deg x 0.25deg gauge-based daily rainfall (Pai et al. 2014),
downloaded directly from IMD via the ``imdlib`` package. This is the gauge-based
reference product for India -- coarser than GSMaP (~28 km vs ~11 km) but ground-
truth rather than satellite estimate.

Grid: lat 6.5-38.5N (129), lon 66.5-100.0E (135). Value = daily total rainfall in
mm (NO x24 conversion, unlike GSMaP). Nodata (ocean / outside India) = -999.
"""
from __future__ import annotations

import imdlib
import numpy as np
import pandas as pd

FILL_BELOW = -900.0   # -999 nodata sentinel
SEASON_MONTHS = [9, 10, 11, 12]


def season_window(year: int, bbox: tuple[float, float, float, float], cache_dir: str):
    """Sep-Dec IMD rainfall (mm/day) over ``bbox`` for one year.

    Returns an xarray DataArray (time, lat, lon) with nodata as NaN. Uses the
    local cache if present (``open_data``), otherwise downloads (``get_data``).
    """
    try:
        d = imdlib.open_data("rain", year, year, "yearwise", file_dir=cache_dir)
    except Exception:
        d = imdlib.get_data("rain", year, year, fn_format="yearwise", file_dir=cache_dir)
    da = d.get_xarray()["rain"]
    da = da.where(da > FILL_BELOW)
    minx, miny, maxx, maxy = bbox
    da = da.sel(lat=slice(miny, maxy), lon=slice(minx, maxx))
    da = da.sel(time=da["time"].dt.month.isin(SEASON_MONTHS))
    return da


def window_axes(da):
    """(lats, lons) 1-D arrays for a season-window DataArray."""
    return np.asarray(da["lat"].values, dtype="float64"), np.asarray(da["lon"].values, dtype="float64")


def season_times(da) -> pd.DatetimeIndex:
    return pd.to_datetime(da["time"].values)
