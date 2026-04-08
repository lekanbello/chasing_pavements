"""
viz.py — Visualize Tanzania road network by surface type.

Produces:
  1. Map of road network colored by surface classification
  2. Bar chart of surface tag coverage by road class
  3. Bar chart of paved/unpaved/unknown km by road class
"""

import os
import sys
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd

# ── Configuration ──────────────────────────────────────────────────────

INPUT_PATH = "data/processed/tanzania_roads.gpkg"
FIG_DIR = "outputs/figures"

SURFACE_COLORS = {
    "paved": "#2166ac",    # blue
    "unpaved": "#b2182b",  # red
    "unknown": "#969696",  # gray
}

# Road classes in order of importance
ROAD_CLASS_ORDER = [
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "unclassified",
    "residential",
    "track",
]


def load_data(path):
    """Load processed road data."""
    print(f"Loading {path}...")
    gdf = gpd.read_file(path)
    print(f"  {len(gdf):,} segments, {gdf['length_km'].sum():,.0f} km")
    return gdf


def plot_road_map(gdf, fig_dir):
    """Map of road network colored by surface classification."""
    print("Plotting road network map...")

    fig, ax = plt.subplots(1, 1, figsize=(12, 14))

    # Plot in order: unknown first (background), then unpaved, then paved on top
    for surface_class in ["unknown", "unpaved", "paved"]:
        subset = gdf[gdf["surface_class"] == surface_class]
        if len(subset) == 0:
            continue
        # Thinner lines for minor roads, thicker for major
        subset.plot(
            ax=ax,
            color=SURFACE_COLORS[surface_class],
            linewidth=0.3,
            alpha=0.7,
        )

    # Legend
    patches = [
        mpatches.Patch(color=SURFACE_COLORS["paved"], label="Paved"),
        mpatches.Patch(color=SURFACE_COLORS["unpaved"], label="Unpaved"),
        mpatches.Patch(color=SURFACE_COLORS["unknown"], label="Unknown"),
    ]
    ax.legend(handles=patches, loc="lower left", fontsize=11, framealpha=0.9)

    # Formatting
    ax.set_title("Tanzania Road Network by Surface Type (OSM)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")

    # Add basic context
    total_km = gdf["length_km"].sum()
    paved_km = gdf.loc[gdf["surface_class"] == "paved", "length_km"].sum()
    unpaved_km = gdf.loc[gdf["surface_class"] == "unpaved", "length_km"].sum()
    unknown_km = gdf.loc[gdf["surface_class"] == "unknown", "length_km"].sum()
    info_text = (
        f"Total: {total_km:,.0f} km\n"
        f"Paved: {paved_km:,.0f} km ({100*paved_km/total_km:.1f}%)\n"
        f"Unpaved: {unpaved_km:,.0f} km ({100*unpaved_km/total_km:.1f}%)\n"
        f"Unknown: {unknown_km:,.0f} km ({100*unknown_km/total_km:.1f}%)"
    )
    ax.text(0.98, 0.98, info_text, transform=ax.transAxes,
            fontsize=9, verticalalignment="top", horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.9))

    plt.tight_layout()
    out_path = os.path.join(fig_dir, "tanzania_road_map.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out_path}")


def plot_coverage_by_class(gdf, fig_dir):
    """Bar chart: surface tag coverage (%) by road class."""
    print("Plotting surface tag coverage by road class...")

    # Compute stats per road class
    classes_in_data = [c for c in ROAD_CLASS_ORDER if c in gdf["highway"].values]
    stats = []
    for cls in classes_in_data:
        subset = gdf[gdf["highway"] == cls]
        total_km = subset["length_km"].sum()
        tagged_km = subset.loc[subset["surface_class"] != "unknown", "length_km"].sum()
        pct = 100 * tagged_km / total_km if total_km > 0 else 0
        stats.append({"highway": cls, "total_km": total_km, "tagged_km": tagged_km, "pct_tagged": pct})
    df = pd.DataFrame(stats)

    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(df["highway"], df["pct_tagged"], color="#4393c3", edgecolor="white")

    # Add km labels on bars
    for bar, row in zip(bars, df.itertuples()):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{row.tagged_km:,.0f}\nof {row.total_km:,.0f} km",
                ha="center", va="bottom", fontsize=7)

    ax.set_ylabel("% of km with Surface Tag")
    ax.set_xlabel("Road Class")
    ax.set_title("OSM Surface Tag Coverage by Road Class — Tanzania", fontweight="bold")
    ax.set_ylim(0, 110)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()

    out_path = os.path.join(fig_dir, "tanzania_surface_coverage.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out_path}")


def plot_surface_by_class(gdf, fig_dir):
    """Stacked bar chart: paved/unpaved/unknown km by road class."""
    print("Plotting surface classification by road class...")

    classes_in_data = [c for c in ROAD_CLASS_ORDER if c in gdf["highway"].values]

    cross = pd.crosstab(
        gdf["highway"], gdf["surface_class"],
        values=gdf["length_km"], aggfunc="sum",
    ).fillna(0)
    cross = cross.reindex(classes_in_data)

    fig, ax = plt.subplots(figsize=(12, 6))

    # Stacked bars
    bottom = pd.Series(0.0, index=cross.index)
    for surface_class in ["paved", "unpaved", "unknown"]:
        if surface_class in cross.columns:
            vals = cross[surface_class]
            ax.bar(cross.index, vals, bottom=bottom,
                   color=SURFACE_COLORS[surface_class], label=surface_class.capitalize(),
                   edgecolor="white", linewidth=0.5)
            bottom += vals

    ax.set_ylabel("Road Length (km)")
    ax.set_xlabel("Road Class")
    ax.set_title("Road Length by Surface Type and Road Class — Tanzania", fontweight="bold")
    ax.legend(loc="upper right")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()

    out_path = os.path.join(fig_dir, "tanzania_surface_by_class.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out_path}")


if __name__ == "__main__":
    if not os.path.exists(INPUT_PATH):
        print(f"Error: {INPUT_PATH} not found. Run ingest.py first.")
        sys.exit(1)

    os.makedirs(FIG_DIR, exist_ok=True)
    gdf = load_data(INPUT_PATH)

    plot_road_map(gdf, FIG_DIR)
    plot_coverage_by_class(gdf, FIG_DIR)
    plot_surface_by_class(gdf, FIG_DIR)

    print("\nDone. All figures saved to outputs/figures/")
