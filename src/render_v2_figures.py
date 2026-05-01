"""
render_v2_figures.py — Regenerate continental + Tanzania figures from v2 results.

Produces:
  outputs/figures/ssa_41_country_welfare.png  — sorted bar chart of Stage 2 welfare
  outputs/figures/ssa_welfare_map.png         — continental choropleth
  outputs/figures/tanzania_district_rankings.png — Tanzania districts ranked
  outputs/figures/tanzania_winners_losers_map.png — Stage 3 redistribution map
"""

import os
import sys
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap

sys.path.insert(0, os.path.dirname(__file__))
from country_config import load_registry, build_config

OUT = "outputs/figures"
os.makedirs(OUT, exist_ok=True)

# Color palette consistent with the deck
TERRACOTTA = "#B85042"
SAGE = "#7CA982"
SLATE = "#475569"
CHARCOAL = "#1F2937"
MUTED = "#64748B"


# ────────────────────────────────────────────────────────────────────────
# Load results
# ────────────────────────────────────────────────────────────────────────

results = pd.read_csv("outputs/ssa_model_results.csv")
results = results[results["status"] == "success"].copy()
results = results.dropna(subset=["welfare_pct"])
results["welfare_pct"] = results["welfare_pct"].astype(float)
results["welfare_s1_pct"] = pd.to_numeric(results["welfare_s1_pct"], errors="coerce")
results["welfare_s3_pct"] = pd.to_numeric(results["welfare_s3_pct"], errors="coerce")
results["welfare_s3_cv"] = pd.to_numeric(results["welfare_s3_cv"], errors="coerce")
print(f"Loaded {len(results)} country results")

# Population-weighted continental headline
total_pop = results["total_population"].sum()
results["pop_weight"] = results["total_population"] / total_pop
continental = (results["welfare_pct"] * results["pop_weight"]).sum()
print(f"Continental Stage 2 (pop-weighted): {continental:+.2f}%")


# ────────────────────────────────────────────────────────────────────────
# Figure 1: 41-country bar chart, sorted by Stage 2 welfare
# ────────────────────────────────────────────────────────────────────────

def render_country_bars():
    df = results.sort_values("welfare_pct", ascending=True)
    n = len(df)

    fig, ax = plt.subplots(figsize=(8, 12), dpi=150)

    # Color bars by Stage 2 welfare on a sequential terracotta scale
    norm = plt.Normalize(vmin=df["welfare_pct"].min(), vmax=df["welfare_pct"].max())
    cmap = LinearSegmentedColormap.from_list("paving", ["#F5E8D3", "#E5A48F", TERRACOTTA, "#7B1F18"])
    colors = [cmap(norm(v)) for v in df["welfare_pct"]]

    bars = ax.barh(range(n), df["welfare_pct"], color=colors, edgecolor="white", linewidth=0.5)

    # Country labels
    ax.set_yticks(range(n))
    ax.set_yticklabels(df["country_name"], fontsize=9)

    # Number annotations
    for i, (val, cv) in enumerate(zip(df["welfare_pct"], df["welfare_s3_cv"])):
        ax.text(val + 0.2, i, f"{val:+.1f}%", va="center", fontsize=8, color=CHARCOAL)

    ax.set_xlabel("Real income (welfare) gain from full paving, %", fontsize=11)
    ax.set_title("Welfare gain from paving every road, by country\n"
                 f"Population-weighted continental average: {continental:+.2f}%",
                 fontsize=12, color=CHARCOAL, pad=12)
    ax.axvline(continental, color=SLATE, linestyle="--", alpha=0.6, linewidth=1)
    ax.text(continental + 0.1, n - 1, f"  continental avg",
            fontsize=9, color=SLATE, va="top", style="italic")

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="x", labelsize=9)
    ax.set_xlim(left=0)
    ax.grid(axis="x", alpha=0.3)
    ax.set_axisbelow(True)

    out = f"{OUT}/ssa_41_country_welfare.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


# ────────────────────────────────────────────────────────────────────────
# Figure 2: Continental choropleth
# ────────────────────────────────────────────────────────────────────────

def render_continental_map():
    """Continental choropleth using Natural Earth admin-0 country boundaries."""
    ne_path = "data/raw/natural_earth/ne_110m_admin_0_countries.shp"
    print(f"Loading country boundaries from {ne_path}...")
    world = gpd.read_file(ne_path)
    africa = world[world["CONTINENT"] == "Africa"].copy()

    # Natural Earth uses ISO_A3 column for ISO3 codes
    africa = africa.rename(columns={"ISO_A3": "iso3"})

    africa = africa.merge(
        results[["iso3", "welfare_pct", "welfare_s3_pct", "welfare_s3_cv"]],
        on="iso3", how="left",
    )
    n_with_results = africa["welfare_pct"].notna().sum()
    print(f"  {len(africa)} African countries; {n_with_results} with results")

    fig, ax = plt.subplots(figsize=(9, 11), dpi=150)
    cmap = LinearSegmentedColormap.from_list("paving", ["#F5E8D3", "#E5A48F", TERRACOTTA, "#7B1F18"])

    africa.plot(
        column="welfare_pct", cmap=cmap, edgecolor="white", linewidth=0.6,
        ax=ax, missing_kwds={"color": "#E5E7EB", "edgecolor": "white"},
        legend=True,
        legend_kwds={
            "label": "Real income (welfare) gain, %",
            "orientation": "horizontal",
            "shrink": 0.6, "pad": 0.05, "aspect": 30,
        },
    )

    ax.set_axis_off()
    ax.set_title("Real income gains from paving every road in Sub-Saharan Africa\n"
                 f"Population-weighted continental average: {continental:+.2f}%",
                 fontsize=12, color=CHARCOAL, pad=12)

    # Annotate the welfare value on each country
    for _, r in africa.iterrows():
        if pd.notna(r["welfare_pct"]):
            cx, cy = r.geometry.representative_point().x, r.geometry.representative_point().y
            ax.annotate(f"{r['welfare_pct']:.0f}", xy=(cx, cy),
                        ha="center", va="center", fontsize=6.5, color=CHARCOAL,
                        path_effects=[])

    out = f"{OUT}/ssa_welfare_map.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Saved: {out}")
    return africa


# ────────────────────────────────────────────────────────────────────────
# Figure 3: Tanzania district rankings (Stage 3 welfare)
# ────────────────────────────────────────────────────────────────────────

def render_tanzania_rankings():
    g = gpd.read_file("data/processed/tanzania_counterfactual.gpkg")
    g["welfare_s3_pct"] = pd.to_numeric(g["welfare_s3_pct"])
    g["pop_s3_pct"] = pd.to_numeric(g["pop_s3_pct"])

    fig, axes = plt.subplots(1, 2, figsize=(14, 7), dpi=150)

    # Top 10 winners
    top = g.nlargest(10, "welfare_s3_pct").iloc[::-1]
    axes[0].barh(range(10), top["welfare_s3_pct"], color=TERRACOTTA, edgecolor="white")
    axes[0].set_yticks(range(10))
    axes[0].set_yticklabels(top["NAME_2"], fontsize=10)
    for i, (w, p) in enumerate(zip(top["welfare_s3_pct"], top["pop_s3_pct"])):
        axes[0].text(w + 0.2, i, f"{w:+.1f}% (pop {p:+.0f}%)", va="center", fontsize=9)
    axes[0].set_xlabel("Welfare gain (%) — Stage 3 frictional mobility")
    axes[0].set_title("Top 10 winners — districts that gain most\nand attract in-migration",
                      fontsize=11, pad=10)
    axes[0].spines["top"].set_visible(False)
    axes[0].spines["right"].set_visible(False)
    axes[0].grid(axis="x", alpha=0.3); axes[0].set_axisbelow(True)
    axes[0].set_xlim(left=0)

    # Bottom 10
    bot = g.nsmallest(10, "welfare_s3_pct").iloc[::-1]
    axes[1].barh(range(10), bot["welfare_s3_pct"], color=SLATE, edgecolor="white")
    axes[1].set_yticks(range(10))
    axes[1].set_yticklabels(bot["NAME_2"], fontsize=10)
    for i, (w, p) in enumerate(zip(bot["welfare_s3_pct"], bot["pop_s3_pct"])):
        axes[1].text(w + 0.1, i, f"{w:+.1f}% (pop {p:+.0f}%)", va="center", fontsize=9)
    axes[1].set_xlabel("Welfare gain (%) — Stage 3 frictional mobility")
    axes[1].set_title("Bottom 10 — disconnected from mainland paving;\nresidents move out toward better-connected districts",
                      fontsize=11, pad=10)
    axes[1].spines["top"].set_visible(False)
    axes[1].spines["right"].set_visible(False)
    axes[1].grid(axis="x", alpha=0.3); axes[1].set_axisbelow(True)
    axes[1].set_xlim(left=0)

    fig.suptitle("Tanzania district welfare gains under frictional mobility (κ=2)",
                 fontsize=13, color=CHARCOAL, y=1.02)

    out = f"{OUT}/tanzania_district_rankings.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


# ────────────────────────────────────────────────────────────────────────
# Figure 4: Tanzania district map (Stage 3 welfare choropleth)
# ────────────────────────────────────────────────────────────────────────

def render_tanzania_district_map():
    g = gpd.read_file("data/processed/tanzania_counterfactual.gpkg")
    g["welfare_s3_pct"] = pd.to_numeric(g["welfare_s3_pct"])

    fig, ax = plt.subplots(figsize=(9, 11), dpi=150)
    cmap = LinearSegmentedColormap.from_list("paving", ["#F5E8D3", "#E5A48F", TERRACOTTA, "#7B1F18"])
    g.plot(column="welfare_s3_pct", cmap=cmap, edgecolor="white", linewidth=0.4,
           ax=ax, legend=True,
           legend_kwds={
               "label": "Real income (welfare) gain, %",
               "orientation": "horizontal",
               "shrink": 0.5, "pad": 0.04, "aspect": 25,
           })
    ax.set_axis_off()
    s2 = float(results.loc[results["iso3"] == "TZA", "welfare_pct"].iloc[0])
    ax.set_title(f"Tanzania: district-level welfare gains under frictional mobility (κ=2)\n"
                 f"Aggregate: {s2:+.1f}% (Stage 2 perfect mobility), redistribution shown above",
                 fontsize=11, color=CHARCOAL, pad=12)

    out = f"{OUT}/tanzania_winners_losers_map.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Saved: {out}")


if __name__ == "__main__":
    render_country_bars()
    render_continental_map()
    render_tanzania_rankings()
    render_tanzania_district_map()
    print("\nAll v2 figures rendered.")
