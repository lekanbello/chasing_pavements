"""
gmaps_fellowship_figure.py — small Google Maps speed-comparison batch
for the fellowship-report deck.

Adapts gmaps_test_v3.py to:
  • Run a tightly-controlled ~16-query batch (8 paved + 8 unpaved, trunk/primary)
  • Save raw output to outputs/gmaps_fellowship_queries.csv
  • Render outputs/figures/gmaps_speed_comparison.png — clean strip+box plot

Stays well under the 10K free-element Routes API quota.
"""

import os
import time
import numpy as np
import pandas as pd
import geopandas as gpd
import requests
import matplotlib.pyplot as plt

API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

ROAD_CLASSES = {"trunk", "primary", "secondary"}  # narrow to cleaner classes
MIN_LEN = 10
MAX_LEN = 50
N_PER_SURFACE = 8       # 8 paved + 8 unpaved = 16 total queries


def load_api_key():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith("GOOGLE_MAPS_API_KEY="):
                    return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ["GOOGLE_MAPS_API_KEY"]


def query_route(o_lat, o_lon, d_lat, d_lon, api_key):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
    }
    body = {
        "origin": {"location": {"latLng": {"latitude": o_lat, "longitude": o_lon}}},
        "destination": {"location": {"latLng": {"latitude": d_lat, "longitude": d_lon}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_UNAWARE",
    }
    r = requests.post(API_URL, headers=headers, json=body, timeout=30)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}"}
    data = r.json()
    if not data.get("routes"):
        return {"error": "no route"}
    route = data["routes"][0]
    dur_s = float(route.get("duration", "0s").rstrip("s"))
    dist_m = route.get("distanceMeters", 0)
    return {
        "gmaps_distance_km": dist_m / 1000,
        "gmaps_duration_hr": dur_s / 3600,
        "gmaps_speed_kmh": (dist_m / 1000) / (dur_s / 3600) if dur_s > 0 else None,
    }


def select_segments():
    print("Loading Tanzania OSM roads...")
    gdf = gpd.read_file("data/processed/tanzania_roads.gpkg")
    print(f"  Total segments: {len(gdf):,}")

    mask = (
        gdf["highway"].isin(ROAD_CLASSES)
        & gdf["surface_class"].isin({"paved", "unpaved"})
        & (gdf["length_km"] >= MIN_LEN)
        & (gdf["length_km"] <= MAX_LEN)
    )
    filt = gdf[mask].copy()
    print(f"  Major roads, {MIN_LEN}-{MAX_LEN}km, known surface: {len(filt)}")

    def endpoints(geom):
        coords = list(geom.coords) if geom.geom_type == "LineString" else list(geom.geoms[0].coords)
        return coords[0], coords[-1]

    rows = []
    for _, r in filt.iterrows():
        try:
            start, end = endpoints(r.geometry)
            rows.append({
                "osm_id": r["osm_id"],
                "highway": r["highway"],
                "surface": r["surface"],
                "surface_class": r["surface_class"],
                "name": r["name"],
                "length_km": r["length_km"],
                "o_lon": start[0], "o_lat": start[1],
                "d_lon": end[0], "d_lat": end[1],
            })
        except Exception:
            continue
    df = pd.DataFrame(rows)

    # Stratify: prefer trunk > primary > secondary; longest first within each
    np.random.seed(7)
    class_order = ["trunk", "primary", "secondary"]
    picks = []
    for surf in ["paved", "unpaved"]:
        sub = df[df.surface_class == surf].copy()
        sub["class_rank"] = sub["highway"].map({c: i for i, c in enumerate(class_order)})
        sub = sub.sort_values(["class_rank", "length_km"], ascending=[True, False])
        picks.append(sub.head(N_PER_SURFACE))
    return pd.concat(picks, ignore_index=True)


def render_figure(df, out_path):
    """Strip + box plot of speeds by surface class. Same-road queries only."""
    same = df[df.same_road].copy()
    fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=150)

    # Layout
    positions = {"paved": 0, "unpaved": 1}
    palette = {"paved": "#1f77b4", "unpaved": "#d62728"}
    for surf in ["paved", "unpaved"]:
        sub = same[same.surface_class == surf]
        x = np.full(len(sub), positions[surf]) + np.random.uniform(-0.10, 0.10, len(sub))
        ax.scatter(x, sub.gmaps_speed_kmh, s=80, alpha=0.7,
                   color=palette[surf], edgecolor="white", linewidth=1.2, zorder=3)

    # Box plot underneath
    box_data = [same[same.surface_class == s].gmaps_speed_kmh.values for s in ["paved", "unpaved"]]
    bp = ax.boxplot(box_data, positions=[0, 1], widths=0.45, patch_artist=True,
                    medianprops=dict(color="black", linewidth=2),
                    boxprops=dict(facecolor="#eeeeee", edgecolor="#888888"),
                    whiskerprops=dict(color="#888888"),
                    capprops=dict(color="#888888"),
                    flierprops=dict(marker=""), zorder=1)

    # Means + line connector
    means = [same[same.surface_class == s].gmaps_speed_kmh.mean() for s in ["paved", "unpaved"]]
    ax.plot([0, 1], means, "o-", color="black", markersize=10, zorder=4, linewidth=2)
    ratio = means[0] / means[1] if means[1] else float("nan")

    # Annotate means
    for pos, m in zip([0, 1], means):
        ax.annotate(f"{m:.0f} km/h", xy=(pos, m), xytext=(pos + 0.15, m),
                    fontsize=11, fontweight="bold", va="center")

    # Annotate ratio
    ax.text(0.5, max(means) + 8, f"Paved is {ratio:.2f}x faster",
            ha="center", fontsize=13, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#fff3cd", edgecolor="#856404"))

    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Paved", "Unpaved"], fontsize=12)
    ax.set_ylabel("Travel speed (km/h)", fontsize=12)
    ax.set_title(
        f"Google Maps travel speeds on Tanzanian road segments\n"
        f"{len(same)} valid queries (length-matched routes only)",
        fontsize=12)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)

    plt.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved figure: {out_path}")


def main():
    api_key = load_api_key()
    print(f"API key loaded: {api_key[:6]}...{api_key[-4:]}\n")

    pairs = select_segments()
    print(f"\nSelected {len(pairs)} segments ({N_PER_SURFACE} paved + {N_PER_SURFACE} unpaved).\n")

    print("Querying Google Maps...\n")
    print(f"{'surface':<10s} {'class':<10s} {'len_km':>8s} {'gm_km':>8s} {'km/h':>8s} {'match':>7s}")
    print("-" * 60)

    results = []
    for _, p in pairs.iterrows():
        r = query_route(p["o_lat"], p["o_lon"], p["d_lat"], p["d_lon"], api_key)
        if "error" in r:
            print(f"{p['surface_class']:<10s} {p['highway']:<10s} {p['length_km']:>8.1f}  ERROR: {r['error']}")
            continue
        match = r["gmaps_distance_km"] / p["length_km"]
        print(f"{p['surface_class']:<10s} {p['highway']:<10s} "
              f"{p['length_km']:>8.1f} {r['gmaps_distance_km']:>8.1f} "
              f"{r['gmaps_speed_kmh']:>8.1f} {match:>7.2f}x")
        results.append({**p.to_dict(), **r, "length_match": match})
        time.sleep(0.1)

    if not results:
        print("No successful queries.")
        return

    df = pd.DataFrame(results)
    df["same_road"] = (df["length_match"] >= 0.7) & (df["length_match"] <= 1.3)

    print("\n" + "=" * 60)
    print("SUMMARY (same-road queries only)")
    print("=" * 60)
    for s in ["paved", "unpaved"]:
        sub = df[(df.surface_class == s) & df.same_road]
        all_sub = df[df.surface_class == s]
        if len(sub) > 0:
            print(f"  {s.upper()}: n={len(sub)}/{len(all_sub)}, mean={sub.gmaps_speed_kmh.mean():.1f} km/h, "
                  f"range {sub.gmaps_speed_kmh.min():.1f}-{sub.gmaps_speed_kmh.max():.1f}")

    same_p = df[(df.surface_class == "paved") & df.same_road]
    same_u = df[(df.surface_class == "unpaved") & df.same_road]
    if len(same_p) > 0 and len(same_u) > 0:
        ratio = same_p.gmaps_speed_kmh.mean() / same_u.gmaps_speed_kmh.mean()
        print(f"\n  Paved/unpaved speed ratio: {ratio:.2f}x")

    csv_out = "outputs/gmaps_fellowship_queries.csv"
    os.makedirs("outputs", exist_ok=True)
    df.to_csv(csv_out, index=False)
    print(f"\nSaved CSV: {csv_out}")

    fig_out = "outputs/figures/gmaps_speed_comparison.png"
    render_figure(df, fig_out)


if __name__ == "__main__":
    main()
