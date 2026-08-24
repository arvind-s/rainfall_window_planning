# 🌧️ Rainfall Window Explorer

A Streamlit app for field staff to plan **plantation timing and field travel**
from satellite/gauge rainfall, analysing the **Sep–Dec** season over the
**last 5 years (2021–2025)** for each project block. Two rainfall sources,
switchable at the top of the app:

- **🛰️ JAXA GSMaP** — satellite estimate, gauge-calibrated, ~11 km
- **🌧️ IMD** — India Meteorological Department rain-gauge grid, ~28 km (ground reference)

Built for the South India Phase-3 agroforestry blocks, but works with any block
polygon shapefile.

## What it shows (per block)

Pure data — no scoring or "suitability" judgement. A **data-source switch** at the
top toggles every view between JAXA GSMaP and IMD. Two week-by-week heatmaps
(rows = weeks Sep 1 → Dec 31, columns = years 2021–2025, plus a 5-yr average):

- **Rainy days per week** — days with rainfall **> 1 mm**
- **Cumulative rainfall per week** — total mm

Plus a weekly detail table (also carrying extreme days **> 5 mm**, dry days
**< 1 mm**, and longest consecutive dry run), a **map** of all blocks coloured by
season rainy days / rainfall, and a **CSV download** of the full weekly-by-year
record. Field staff read the patterns directly to plan plantation and travel.

## Data

**JAXA GSMaP** — satellite:
- *Gauge-calibrated* daily product, v6 standard, pulled **directly from the JAXA
  FTP** (`hokusai.eorc.jaxa.jp`) — no Earth Engine. 0.1° (~11 km).
- The raw grid stores daily-mean rain *rate* in mm/hr; the pipeline converts to
  **mm/day** (× 24). Negative values (−999.9) are treated as missing.

**IMD** — rain-gauge grid:
- IMD Pune 0.25° (~28 km) gauge-based daily rainfall (Pai et al. 2014), pulled via
  the **`imdlib`** package. Value is **mm/day** directly. Nodata (−999, over sea) →
  NaN; coastal blocks whose cell falls on water are snapped to the nearest land cell.

Each block's daily value is the **mean of the grid cells inside the polygon**
(nearest cell for blocks smaller than one grid cell).

## Setup

```bash
pip install -r requirements.txt
```

## 1. Build the dataset (run once; yearly to refresh)

```bash
python build_dataset.py --years 2021 2022 2023 2024 2025
```

Builds **both sources** by default (`--sources gsmap imd` to pick). GSMaP is
FTP-bound (~1 hr first run); IMD downloads five small year-files. Writes per-source
tables to `data/out/`:

| file | contents |
|------|----------|
| `daily_<src>.parquet` | block × date daily rainfall (mm) |
| `weekly_by_year_<src>.parquet` | block × year × week metrics |
| `climatology_<src>.parquet` | block × week 5-yr averages |
| `blocks.geojson` | block boundaries (shared) |

where `<src>` is `gsmap` or `imd`. GSMaP windows cache under `data/raw_cache/`
(~few MB) and IMD year-files under `data/imd_cache/`, so re-runs skip
already-downloaded data and the multi-GB global GSMaP files are never stored.

Quick validation run (10 days of one year, one source):

```bash
python build_dataset.py --years 2024 --sources imd --max-days 10 --out data/out_test
```

## 2. Run the app

```bash
streamlit run app.py
```

Pick **State → District → Block** (or click a block on the map) and toggle the
**rainfall source** (JAXA GSMaP / IMD) at the top. The URL carries
`?block=<name>` so a specific block view can be shared.

## 3. Deploy to Streamlit Community Cloud

The app reads the **baked `data/out/` files** (committed to this repo, ~2.6 MB) —
it does **not** download rainfall at runtime, so no FTP/IMD access is needed on the
server. To deploy:

1. Push this directory to a GitHub repo (see below).
2. On [share.streamlit.io](https://share.streamlit.io) → **New app**, pick the repo,
   set **Main file path** to `app.py`, and deploy.

Streamlit Cloud installs `requirements.txt` (runtime only). To refresh the data
later, rebuild locally with `requirements-build.txt` and push the updated
`data/out/` files.

## Weeks

Fixed 7-day bins from Sep 1 (Week 1 = Sep 1–7, …). The season is 122 days, so
the final bin (Dec 29–31) is a 3-day partial week, flagged `is_full_week=False`.

## Project layout

```
rainfall_app/
├── rainfall/           # library
│   ├── gsmap.py        #   JAXA FTP access + binary grid parsing
│   ├── imd.py          #   IMD gridded rainfall via imdlib
│   ├── metrics.py      #   weekly binning, thresholds, dry spells
│   └── blocks.py       #   shapefile loading + polygon→pixel mapping
├── build_dataset.py       # offline data-prep pipeline (both sources)
├── app.py                 # Streamlit app (entry point)
├── tests/                 # unit tests (pytest)
├── data/out/              # baked dataset (committed -- read at runtime)
├── .streamlit/config.toml # theme
├── requirements.txt       # runtime deps (Streamlit Cloud)
└── requirements-build.txt # + imdlib, for rebuilding data locally
```

## Tests

```bash
python -m pytest tests/ -q
```
