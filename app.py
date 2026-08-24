#!/usr/bin/env python3
"""Rainfall Window Explorer -- JAXA GSMaP + IMD Sep-Dec analysis for field staff.

A clean, one-view-at-a-time dashboard. Choose a rainfall source at the top:
    * JAXA GSMaP -- satellite estimate, gauge-calibrated, ~11 km
    * IMD        -- rain-gauge gridded, ~28 km (ground reference for India)

Then, per block, over the last 5 years:
    * Rainy days per week (> 1 mm)      -- weekly heatmap
    * Cumulative rainfall per week (mm) -- weekly heatmap
    * A map of all blocks, and the raw weekly data table.

Pure data -- no scoring or 'suitability' judgement.

Run:  streamlit run app.py
"""
from __future__ import annotations

import os

import branca.colormap as cm
import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from rainfall import metrics

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("RAINFALL_OUT", os.path.join(HERE, "data", "out"))

st.set_page_config(page_title="Rainfall Window Explorer",
                   page_icon="🌧️", layout="wide",
                   initial_sidebar_state="expanded")

# ---- rainfall sources -----------------------------------------------------
SOURCES = {
    "🛰️ JAXA GSMaP": {"key": "gsmap", "res": "satellite estimate, gauge-calibrated · ~11 km"},
    "🌧️ IMD gauge grid": {"key": "imd", "res": "rain-gauge gridded, IMD Pune · ~28 km"},
}

# ---- palette (sequential, single-hue ramps) -------------------------------
INK, MUTED, LINE = "#1f2937", "#64748b", "#cbd5e1"
DAYS_RAMP = ["#eef4fb", "#cfe1f2", "#9dc3e3", "#5a9bd4", "#2b6cb0", "#1a4f8a"]   # blues
RAIN_RAMP = ["#eff7f6", "#cdeae6", "#93d3cb", "#4db6ac", "#128577", "#0b5c52"]   # teals
PLOT_FONT = dict(family="Source Sans Pro, Segoe UI, sans-serif", color=INK, size=13)

MAP_METRICS = {
    "Rainy days (Sep–Dec, 5-yr avg)": ("season_rainy", "days", DAYS_RAMP),
    "Rainfall (Sep–Dec, 5-yr avg)": ("season_mm", "mm", RAIN_RAMP),
}

CSS = """
<style>
#MainMenu, footer, header {visibility: hidden;}
.block-container {padding-top: 2.2rem; padding-bottom: 2rem; max-width: 1150px;}
h1, h2, h3 {font-family: 'Source Sans Pro', 'Segoe UI', sans-serif; color: #0f172a;}
div[data-testid="stMetric"] {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 14px 18px;}
div[data-testid="stMetricLabel"] p {color: #64748b; font-size: .8rem;}
div[data-testid="stMetricValue"] {color: #0f172a; font-weight: 600; font-size: 1.7rem;}
button[data-baseweb="tab"] {font-size: 1rem; font-weight: 600;}
.stTabs [data-baseweb="tab-list"] {gap: 4px;}
.app-caption {color:#64748b; font-size:.9rem; margin:-6px 0 4px 0;}
</style>
"""


@st.cache_data(show_spinner=False)
def load_blocks():
    return gpd.read_file(os.path.join(OUT, "blocks.geojson"))


@st.cache_data(show_spinner=False)
def load_source(key):
    clim = pd.read_parquet(os.path.join(OUT, f"climatology_{key}.parquet"))
    wby = pd.read_parquet(os.path.join(OUT, f"weekly_by_year_{key}.parquet"))
    agg = clim.groupby("block").agg(
        season_rainy=("mean_rainy_days", "sum"),
        season_mm=("mean_total_mm", "sum")).reset_index()
    return clim, wby, agg


def styled_heatmap(wby_block, value_col, ramp, unit, val_fmt, zmax=None):
    """Professional week (rows, Sep->Dec) x year (cols) heatmap."""
    pivot = wby_block.pivot_table(index="week", columns="year",
                                  values=value_col, aggfunc="first").sort_index()
    years = [str(int(y)) for y in pivot.columns]
    avg = pivot.mean(axis=1)
    z = [list(r) + [a] for r, a in zip(pivot.values, avg.values)]
    xcols = years + ["5-yr avg"]
    ylabels = [metrics.week_label(int(w)) for w in pivot.index]
    zt = float(zmax) if zmax else float(np.nanmax(z) or 1)

    fig = go.Figure(go.Heatmap(
        z=z, x=xcols, y=ylabels, colorscale=ramp, zmin=0, zmax=zt,
        xgap=3, ygap=3, hoverongaps=False,
        colorbar=dict(title=dict(text=unit, side="right"), thickness=13,
                      len=0.9, outlinewidth=0, tickcolor=LINE, ticklen=4),
        hovertemplate="<b>%{y}</b><br>%{x}: %{z:.1f} " + unit + "<extra></extra>"))

    anns = []  # per-cell labels; anchor by INTEGER index (year strings would
    for i, wk in enumerate(ylabels):          # coerce to numbers and break the axis)
        for j in range(len(xcols)):
            v = z[i][j]
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            frac = v / zt if zt else 0
            anns.append(dict(x=j, y=i, xref="x", yref="y", text=val_fmt(v),
                             showarrow=False,
                             font=dict(color="white" if frac > 0.6 else INK, size=11)))

    fig.update_layout(
        annotations=anns, font=PLOT_FONT, height=26 * len(ylabels) + 120,
        margin=dict(t=52, b=10, l=8, r=8), paper_bgcolor="white", plot_bgcolor="white",
        yaxis=dict(autorange="reversed", showgrid=False, ticks="", tickfont=dict(color=MUTED)),
        xaxis=dict(type="category", side="top", showgrid=False, ticks="",
                   tickfont=dict(color=INK, size=12)))
    fig.add_vline(x=len(years) - 0.5, line_width=1.5, line_color="#94a3b8", line_dash="dot")
    return fig


# --------------------------------------------------------------------------
st.markdown(CSS, unsafe_allow_html=True)

if not os.path.exists(os.path.join(OUT, "climatology_gsmap.parquet")):
    st.title("🌧️ Rainfall Window Explorer")
    st.warning("Dataset not built yet. Run `python build_dataset.py` first.")
    st.stop()

blocks_geo = load_blocks()
block_names = sorted(blocks_geo["block"].dropna().unique())
info = blocks_geo.set_index("block")[["state", "district"]].to_dict("index")

# ---- selection state (dropdowns + map click share one selected block) -----
pending = st.session_state.pop("_pending_block", None)
if pending is None:
    qp_block = st.query_params.get("block")
    if qp_block in info and "sel_block" not in st.session_state:
        pending = qp_block
if pending in info:
    st.session_state["sel_state"] = info[pending]["state"]
    st.session_state["sel_district"] = info[pending]["district"]
    st.session_state["sel_block"] = pending

with st.sidebar:
    st.markdown("### 🌧️ Rainfall Window")
    st.caption("Sep–Dec · 2021–2025")
    st.divider()
    st.markdown("**Select a block**")
    states = sorted(blocks_geo["state"].dropna().unique())
    state = st.selectbox("State", states, key="sel_state")

    dsub = blocks_geo[blocks_geo["state"] == state]
    districts = sorted(dsub["district"].dropna().unique())
    if st.session_state.get("sel_district") not in districts:
        st.session_state["sel_district"] = districts[0]
    district = st.selectbox("District", districts, key="sel_district")

    bsub = dsub[dsub["district"] == district]
    bopts = sorted(bsub["block"].dropna().unique())
    if st.session_state.get("sel_block") not in bopts:
        st.session_state["sel_block"] = bopts[0]
    block = st.selectbox("Block", bopts, key="sel_block")

st.query_params["block"] = block

# ---- header + data-source switch ------------------------------------------
st.title("Rainfall Window Explorer")
src_label = st.segmented_control("Rainfall source", list(SOURCES),
                                 default=list(SOURCES)[0], label_visibility="collapsed")
if not src_label:
    src_label = list(SOURCES)[0]
src = SOURCES[src_label]
clim, wby, agg = load_source(src["key"])
blocks = blocks_geo.merge(agg, on="block", how="left")

st.markdown(
    f"<div class='app-caption'><b>{block}</b> · {district}, {state} &nbsp;|&nbsp; "
    f"Source: <b>{src_label.split(' ', 1)[1]}</b> ({src['res']}) · Sep–Dec 2021–2025</div>",
    unsafe_allow_html=True)
st.write("")

clim_b = clim[clim["block"] == block].sort_values("week")
wby_b = wby[wby["block"] == block].sort_values(["week", "year"])
full = clim_b[clim_b["is_full_week"]]

# ---- KPI strip ------------------------------------------------------------
wettest = full.loc[full["mean_rainy_days"].idxmax()] if len(full) else None
k1, k2, k3, k4 = st.columns(4)
k1.metric("Rainy days", f"{full['mean_rainy_days'].sum():.0f}",
          help="Total days >1mm across Sep–Dec, 5-yr average")
k2.metric("Rainfall", f"{full['mean_total_mm'].sum():.0f} mm",
          help="Total rainfall across Sep–Dec, 5-yr average")
k3.metric("Wettest week", metrics.week_label(int(wettest["week"])) if wettest is not None else "–",
          help="Week with the most rainy days on average")
k4.metric("Longest dry run", f"{full['mean_longest_dry_run'].max():.0f} days",
          help="Longest consecutive dry-day run in any week, 5-yr average")
st.write("")

# ---- tabs (one view at a time) --------------------------------------------
tab_days, tab_rain, tab_map, tab_data = st.tabs(
    ["🔵  Rainy days", "🟢  Cumulative rainfall", "🗺️  Map", "📋  Data"])

with tab_days:
    st.markdown("##### Rainy days per week &nbsp;·&nbsp; days with rainfall > 1 mm")
    st.caption("Rows: weeks Sep 1 → Dec 31 · Columns: each year and the 5-year average "
               "(right of the dotted line). Darker = more rainy days.")
    st.plotly_chart(styled_heatmap(wby_b, "rainy_days", DAYS_RAMP, "days",
                                   lambda v: f"{v:.0f}", zmax=7),
                    use_container_width=True, config={"displayModeBar": False})

with tab_rain:
    st.markdown("##### Cumulative rainfall per week &nbsp;·&nbsp; total mm")
    st.caption("Rows: weeks Sep 1 → Dec 31 · Columns: each year and the 5-year average "
               "(right of the dotted line). Darker = more rainfall.")
    st.plotly_chart(styled_heatmap(wby_b, "total_mm", RAIN_RAMP, "mm", lambda v: f"{v:.0f}"),
                    use_container_width=True, config={"displayModeBar": False})

with tab_map:
    st.markdown("##### Block map")
    mlabel = st.radio("Colour by", list(MAP_METRICS), horizontal=True, label_visibility="collapsed")
    mcol, munit, mramp = MAP_METRICS[mlabel]
    st.caption(f"Colour = {mlabel.lower()} · {src_label}. Click a block to select it.")

    vmin, vmax = float(blocks[mcol].min()), float(blocks[mcol].max())
    if vmax - vmin < 1e-9:
        vmax = vmin + 1.0
    colormap = cm.LinearColormap(mramp, vmin=vmin, vmax=vmax, caption=mlabel)
    sel = blocks[blocks["block"] == block]
    center = [sel.geometry.centroid.y.iloc[0], sel.geometry.centroid.x.iloc[0]]
    fmap = folium.Map(location=center, zoom_start=7, tiles="CartoDB positron")
    folium.GeoJson(
        blocks.__geo_interface__,
        style_function=lambda f: {
            "fillColor": colormap(f["properties"][mcol]) if f["properties"].get(mcol) is not None else "#e2e8f0",
            "color": "#94a3b8", "weight": 0.6, "fillOpacity": 0.8},
        highlight_function=lambda f: {"weight": 2.5, "color": "#0f172a", "fillOpacity": 0.95},
        tooltip=folium.GeoJsonTooltip(fields=["block", "district", "state", mcol],
                                      aliases=["Block", "District", "State", mlabel], localize=True),
    ).add_to(fmap)
    folium.GeoJson(sel.__geo_interface__,
                   style_function=lambda f: {"color": "#dc2626", "weight": 3, "fillOpacity": 0.0}).add_to(fmap)
    colormap.add_to(fmap)
    out = st_folium(fmap, height=560, use_container_width=True,
                    returned_objects=["last_active_drawing"])
    clicked = (out or {}).get("last_active_drawing")
    if clicked and clicked.get("properties", {}).get("block") in block_names:
        cb = clicked["properties"]["block"]
        if cb != block:
            st.session_state["_pending_block"] = cb
            st.rerun()

with tab_data:
    st.markdown("##### Weekly detail")
    view = st.radio("View", ["5-year average", "Year by year"], horizontal=True,
                    label_visibility="collapsed")
    if view == "5-year average":
        t = clim_b.copy()
        t["Week"] = t["week"].apply(lambda w: metrics.week_label(int(w)))
        show = t[["Week", "mean_rainy_days", "mean_total_mm", "mean_extreme_days",
                  "mean_dry_days", "mean_longest_dry_run", "n_years"]].round(1).rename(columns={
            "mean_rainy_days": "Rainy days", "mean_total_mm": "Rain (mm)",
            "mean_extreme_days": "Extreme days", "mean_dry_days": "Dry days",
            "mean_longest_dry_run": "Longest dry run", "n_years": "Years"})
    else:
        t = wby_b.copy()
        t["Week"] = t["week"].apply(lambda w: metrics.week_label(int(w)))
        show = t[["year", "Week", "rainy_days", "total_mm", "extreme_days",
                  "dry_days", "longest_dry_run", "n_days"]].round(1).rename(columns={
            "year": "Year", "rainy_days": "Rainy days", "total_mm": "Rain (mm)",
            "extreme_days": "Extreme days", "dry_days": "Dry days",
            "longest_dry_run": "Longest dry run", "n_days": "Days"})
    st.dataframe(show, use_container_width=True, hide_index=True)

    dl = wby_b[["year", "week", "rainy_days", "total_mm", "extreme_days",
                "dry_days", "longest_dry_run", "n_days"]].copy()
    dl.insert(2, "week_range", dl["week"].apply(lambda w: metrics.week_label(int(w))))
    st.download_button(f"⬇️  Download {block} · {src['key'].upper()} weekly table (CSV)",
                       dl.to_csv(index=False).encode(),
                       file_name=f"rainfall_{src['key']}_{block.replace(' ', '_')}.csv",
                       mime="text/csv")
