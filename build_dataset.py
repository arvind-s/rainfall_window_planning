#!/usr/bin/env python3
"""Build the baked rainfall datasets the Streamlit app reads.

Two rainfall sources, each fetched directly (no Earth Engine):
  * gsmap -- JAXA GSMaP gauge-calibrated daily, 0.1deg, via JAXA FTP
  * imd   -- IMD Pune gauge-based daily, 0.25deg, via the imdlib package

For the Sep-Dec season of each requested year, computes block-mean daily rainfall
for every block in the shapefile, then writes per-source tables to data/out/:

    daily_<src>.parquet          block x date daily rainfall (mm)
    weekly_by_year_<src>.parquet block x year x week metrics
    climatology_<src>.parquet    block x week 5-yr averages (descriptive)
    blocks.geojson               block boundaries (shared, geometry + names)

Usage:
    python build_dataset.py                          # both sources, 2021-2025
    python build_dataset.py --sources imd
    python build_dataset.py --sources gsmap --max-days 10   # quick validation
"""
from __future__ import annotations

import argparse
import ftplib
import os
import sys
import time

import numpy as np
import pandas as pd

from rainfall import gsmap, imd, metrics, blocks as blk

DEFAULT_SHP = ("/Users/mipl/Documents/Agroforestry/South India/Phase 3/"
               "Stratification/Input_boundary/Blocks/SI_blocks_3rd_phase_updated_6.shp")
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data", "raw_cache")
IMD_CACHE = os.path.join(HERE, "data", "imd_cache")
OUT = os.path.join(HERE, "data", "out")


def _block_means(grid, pixel_map) -> dict:
    """Mean over each block's pixels for one 2-D (lat, lon) rainfall grid."""
    out = {}
    for name, px in pixel_map.items():
        vals = np.array([grid[r, c] for r, c in px], dtype="float64")
        out[name] = float(np.nanmean(vals)) if np.isfinite(vals).any() else np.nan
    return out


def build_daily_gsmap(years, blocks, bbox, max_days=None) -> pd.DataFrame:
    ftp = ftplib.FTP(gsmap.FTP_HOST, timeout=120)
    ftp.login(gsmap.FTP_USER, gsmap.FTP_PASS)
    pixel_map, records = None, []
    try:
        for year in years:
            dates = metrics.season_dates(year)
            if max_days:
                dates = dates[:max_days]
            t0 = time.time()
            for i, d in enumerate(dates):
                try:
                    win = gsmap.fetch_window(d, bbox, CACHE, ftp=ftp)
                except FileNotFoundError as e:
                    print(f"  ! {d} missing on server ({e})")
                    continue
                except (ftplib.error_perm, EOFError, OSError) as e:
                    print(f"  ! {d} conn error ({e.__class__.__name__}); reconnecting")
                    try:
                        ftp.quit()
                    except Exception:
                        pass
                    ftp = ftplib.FTP(gsmap.FTP_HOST, timeout=120)
                    ftp.login(gsmap.FTP_USER, gsmap.FTP_PASS)
                    gsmap._DIR_CACHE.clear()
                    continue
                if pixel_map is None:
                    pixel_map = blk.build_pixel_map(blocks, win["lats"], win["lons"])
                    npx = {k: len(v) for k, v in pixel_map.items()}
                    print(f"  gsmap pixel map: {min(npx.values())}-{max(npx.values())} cells/block")
                for name, m in _block_means(win["data"], pixel_map).items():
                    records.append((name, d, m))
                if (i + 1) % 30 == 0 or i == len(dates) - 1:
                    print(f"  gsmap {year}: {i+1}/{len(dates)} days ({time.time()-t0:.0f}s)", flush=True)
    finally:
        try:
            ftp.quit()
        except Exception:
            pass
    df = pd.DataFrame(records, columns=["block", "date", "rain_mm"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def build_daily_imd(years, blocks, bbox, max_days=None) -> pd.DataFrame:
    pixel_map, records = None, []
    for year in years:
        da = imd.season_window(year, bbox, IMD_CACHE)
        lats, lons = imd.window_axes(da)
        data = da.values  # (time, lat, lon)
        if pixel_map is None:
            # IMD is nodata over sea -> restrict to land cells (valid on any day)
            valid = np.isfinite(data).any(axis=0)
            pixel_map = blk.build_pixel_map(blocks, lats, lons, valid_mask=valid)
            npx = {k: len(v) for k, v in pixel_map.items()}
            print(f"  imd pixel map: {min(npx.values())}-{max(npx.values())} cells/block "
                  f"({int(valid.sum())} land cells)")
        times = imd.season_times(da)
        if max_days:
            times, data = times[:max_days], data[:max_days]
        for ti, t in enumerate(times):
            for name, m in _block_means(data[ti], pixel_map).items():
                records.append((name, t, m))
        print(f"  imd {year}: {len(times)} days", flush=True)
    df = pd.DataFrame(records, columns=["block", "date", "rain_mm"])
    df["date"] = pd.to_datetime(df["date"])
    return df


BUILDERS = {"gsmap": build_daily_gsmap, "imd": build_daily_imd}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="+", default=[2021, 2022, 2023, 2024, 2025])
    ap.add_argument("--sources", nargs="+", choices=["gsmap", "imd"], default=["gsmap", "imd"])
    ap.add_argument("--shp", default=DEFAULT_SHP)
    ap.add_argument("--max-days", type=int, default=None)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    os.makedirs(IMD_CACHE, exist_ok=True)
    blocks = blk.load_blocks(args.shp)
    bbox = blk.season_bbox(blocks)
    print(f"Loaded {len(blocks)} blocks; window bbox = {tuple(round(v,2) for v in bbox)}")
    blocks.to_file(os.path.join(args.out, "blocks.geojson"), driver="GeoJSON")

    for src in args.sources:
        print(f"=== building {src} ===")
        daily = BUILDERS[src](args.years, blocks, bbox, args.max_days)
        print(f"  {src} daily rows: {len(daily)} | NaN means: {daily['rain_mm'].isna().sum()} "
              f"| mm/day range {daily['rain_mm'].min():.1f}..{daily['rain_mm'].max():.1f}")
        wby = metrics.weekly_by_year(daily)
        clim = metrics.climatology(wby)
        daily.to_parquet(os.path.join(args.out, f"daily_{src}.parquet"), index=False)
        wby.to_parquet(os.path.join(args.out, f"weekly_by_year_{src}.parquet"), index=False)
        clim.to_parquet(os.path.join(args.out, f"climatology_{src}.parquet"), index=False)
        print(f"  wrote daily_{src} / weekly_by_year_{src} / climatology_{src} parquet")

    print("Done ->", args.out)


if __name__ == "__main__":
    sys.exit(main())
