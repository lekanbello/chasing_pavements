"""
ingest.py — Download and process OSM road data for Tanzania.

Extracts road network from PBF, analyzes surface tag coverage,
classifies roads as paved/unpaved/unknown, and saves processed data.
"""

import os
import sys
import osmium
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString

# ── Configuration ──────────────────────────────────────────────────────

PBF_PATH = "data/raw/tanzania-latest.osm.pbf"
OUTPUT_PATH = "data/processed/tanzania_roads.gpkg"

# Road classes relevant for inter-city and intra-country travel
ROAD_CLASSES = {
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "unclassified",
    "residential",
    "track",
}

# Surface tag → binary classification
PAVED_SURFACES = {
    "paved", "asphalt", "concrete", "concrete:plates", "concrete:lanes",
    "sett", "cobblestone", "metal", "wood", "bricks",
}
UNPAVED_SURFACES = {
    "unpaved", "gravel", "fine_gravel", "compacted", "dirt", "earth",
    "grass", "ground", "mud", "sand", "soil", "rock",
}


def classify_surface(surface_tag):
    """Classify a raw OSM surface tag into paved/unpaved/unknown."""
    if surface_tag is None or surface_tag == "":
        return "unknown"
    tag = surface_tag.strip().lower()
    if tag in PAVED_SURFACES:
        return "paved"
    elif tag in UNPAVED_SURFACES:
        return "unpaved"
    else:
        return "unknown"


# ── OSM Handler ────────────────────────────────────────────────────────

class RoadHandler(osmium.SimpleHandler):
    """Extract road ways from OSM PBF with surface and highway tags."""

    def __init__(self):
        super().__init__()
        self.roads = []

    def way(self, w):
        highway = w.tags.get("highway")
        if highway not in ROAD_CLASSES:
            return

        # Build geometry from node locations
        try:
            coords = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            return

        if len(coords) < 2:
            return

        self.roads.append({
            "osm_id": w.id,
            "highway": highway,
            "surface": w.tags.get("surface"),
            "name": w.tags.get("name"),
            "geometry": LineString(coords),
        })


# ── Main Pipeline ──────────────────────────────────────────────────────

def extract_roads(pbf_path):
    """Parse PBF and return a GeoDataFrame of roads."""
    print(f"Reading {pbf_path}...")
    handler = RoadHandler()
    handler.apply_file(pbf_path, locations=True)
    print(f"  Extracted {len(handler.roads):,} road segments")

    gdf = gpd.GeoDataFrame(handler.roads, crs="EPSG:4326")

    # Classify surface
    gdf["surface_class"] = gdf["surface"].apply(classify_surface)

    # Compute length in km (project to UTM zone 37S for Tanzania)
    gdf_proj = gdf.to_crs("EPSG:32737")
    gdf["length_km"] = gdf_proj.geometry.length / 1000.0

    return gdf


def print_summary(gdf):
    """Print comprehensive summary statistics."""
    total_segments = len(gdf)
    total_km = gdf["length_km"].sum()

    print("\n" + "=" * 70)
    print("TANZANIA OSM ROAD NETWORK — SUMMARY")
    print("=" * 70)

    # ── Overall ──
    print(f"\nTotal segments:  {total_segments:>10,}")
    print(f"Total length:    {total_km:>10,.0f} km")

    # ── By road class ──
    print("\n── By Road Class ─────────────────────────────────────────────")
    class_stats = (
        gdf.groupby("highway")
        .agg(segments=("osm_id", "count"), km=("length_km", "sum"))
        .sort_values("km", ascending=False)
    )
    class_stats["pct_km"] = 100 * class_stats["km"] / total_km
    print(class_stats.to_string(
        formatters={"segments": "{:,}".format, "km": "{:,.0f}".format, "pct_km": "{:.1f}%".format}
    ))

    # ── Surface tag coverage ──
    print("\n── Surface Tag Coverage ──────────────────────────────────────")
    has_tag = gdf["surface"].notna() & (gdf["surface"] != "")
    n_tagged = has_tag.sum()
    km_tagged = gdf.loc[has_tag, "length_km"].sum()
    print(f"Segments with surface tag:  {n_tagged:>8,} / {total_segments:,}  ({100*n_tagged/total_segments:.1f}%)")
    print(f"Km with surface tag:        {km_tagged:>8,.0f} / {total_km:,.0f}  ({100*km_tagged/total_km:.1f}%)")

    # ── Raw surface values ──
    print("\n── Raw Surface Tag Values (top 20) ───────────────────────────")
    surface_counts = (
        gdf[has_tag]
        .groupby("surface")
        .agg(segments=("osm_id", "count"), km=("length_km", "sum"))
        .sort_values("km", ascending=False)
        .head(20)
    )
    print(surface_counts.to_string(
        formatters={"segments": "{:,}".format, "km": "{:,.0f}".format}
    ))

    # ── Binary classification ──
    print("\n── Surface Classification (paved / unpaved / unknown) ───────")
    class_counts = (
        gdf.groupby("surface_class")
        .agg(segments=("osm_id", "count"), km=("length_km", "sum"))
        .sort_values("km", ascending=False)
    )
    class_counts["pct_segments"] = 100 * class_counts["segments"] / total_segments
    class_counts["pct_km"] = 100 * class_counts["km"] / total_km
    print(class_counts.to_string(
        formatters={
            "segments": "{:,}".format, "km": "{:,.0f}".format,
            "pct_segments": "{:.1f}%".format, "pct_km": "{:.1f}%".format,
        }
    ))

    # ── Cross-tabulation: surface class × road class ──
    print("\n── Surface Class × Road Class (km) ──────────────────────────")
    cross = pd.crosstab(
        gdf["highway"], gdf["surface_class"],
        values=gdf["length_km"], aggfunc="sum",
    ).fillna(0)
    cross["total"] = cross.sum(axis=1)
    cross = cross.sort_values("total", ascending=False)

    # Add % tagged column
    if "unknown" in cross.columns:
        cross["pct_tagged"] = 100 * (1 - cross["unknown"] / cross["total"])
    print(cross.to_string(float_format="{:,.0f}".format))

    # ── Surface coverage by road class ──
    print("\n── Surface Tag Coverage by Road Class ────────────────────────")
    for cls in cross.index:
        total_cls = cross.loc[cls, "total"]
        tagged = total_cls - cross.loc[cls].get("unknown", 0)
        pct = 100 * tagged / total_cls if total_cls > 0 else 0
        print(f"  {cls:20s}  {tagged:>8,.0f} / {total_cls:>8,.0f} km  ({pct:5.1f}% tagged)")

    print("\n" + "=" * 70)


def save_data(gdf, output_path):
    """Save processed GeoDataFrame."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    gdf.to_file(output_path, driver="GPKG")
    size_mb = os.path.getsize(output_path) / 1e6
    print(f"\nSaved to {output_path} ({size_mb:.0f} MB)")


if __name__ == "__main__":
    if not os.path.exists(PBF_PATH):
        print(f"Error: {PBF_PATH} not found. Download it first.")
        sys.exit(1)

    gdf = extract_roads(PBF_PATH)
    print_summary(gdf)
    save_data(gdf, OUTPUT_PATH)
