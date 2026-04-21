"""
gmaps_test_v3.py — Paved vs unpaved test using OSM road segments directly.

Picks long individual OSM road segments with explicit paved/unpaved surface tags
and queries Google Maps between their endpoints. This avoids the centroid-routing
ambiguity: if Google's returned distance matches the OSM segment length,
Google is using the same road and speeds directly reflect surface.

Usage:
    python3 src/gmaps_test_v3.py
"""

import os
import time
import numpy as np
import pandas as pd
import geopandas as gpd
import requests


API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

# Only use major road classes to avoid residential/track mislabels
ROAD_CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary"}

# Segment length filter (km)
MIN_LEN = 10
MAX_LEN = 50  # avoid very long ways that might cross regions


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
    """Select long OSM road segments with known paved/unpaved tags."""
    print("Loading Tanzania OSM roads...")
    gdf = gpd.read_file("data/processed/tanzania_roads.gpkg")
    print(f"  Total segments: {len(gdf):,}")

    # Filter to major road classes, known surface, in target length range
    mask = (
        gdf["highway"].isin(ROAD_CLASSES)
        & gdf["surface_class"].isin({"paved", "unpaved"})
        & (gdf["length_km"] >= MIN_LEN)
        & (gdf["length_km"] <= MAX_LEN)
    )
    filt = gdf[mask].copy()
    print(f"  Major roads, {MIN_LEN}–{MAX_LEN}km, known surface: {len(filt)}")

    # Breakdown
    print("\n  By surface class:")
    print(filt.groupby(["surface_class", "highway"]).size().unstack(fill_value=0))

    # Extract endpoint coordinates
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

    # Pick 5 paved + 5 unpaved, preferring trunk/primary for cleaner signal
    np.random.seed(42)
    class_order = ["trunk", "primary", "secondary", "tertiary"]

    picks = []
    for surf in ["paved", "unpaved"]:
        sub = df[df.surface_class == surf].copy()
        sub["class_rank"] = sub["highway"].map({c: i for i, c in enumerate(class_order)})
        sub = sub.sort_values(["class_rank", "length_km"], ascending=[True, False])
        picks.append(sub.head(5))

    return pd.concat(picks, ignore_index=True)


def main():
    api_key = load_api_key()
    masked = api_key[:6] + "..." + api_key[-4:]
    print(f"API key loaded: {masked}\n")

    pairs = select_segments()

    print("\nSelected OSM segments:")
    print(f"{'highway':<10s} {'surface_class':<13s} {'surface':<15s} {'len(km)':>8s} {'name':<30s}")
    print("-" * 78)
    for _, r in pairs.iterrows():
        name = str(r.get("name", ""))[:28]
        print(f"{r['highway']:<10s} {r['surface_class']:<13s} {str(r['surface'])[:14]:<15s} "
              f"{r['length_km']:>8.1f} {name:<30s}")

    print("\nQuerying Google Maps...\n")
    print(f"{'OSM':<10s} {'class':<10s} {'len_km':>8s} {'gm_km':>8s} {'hr':>6s} {'km/h':>8s} {'match':>7s}")
    print("-" * 78)

    results = []
    for _, p in pairs.iterrows():
        r = query_route(p["o_lat"], p["o_lon"], p["d_lat"], p["d_lon"], api_key)
        if "error" in r:
            print(f"{p['surface_class']:<10s} {p['highway']:<10s} {p['length_km']:>8.1f}  ERROR: {r['error']}")
            continue
        match = r["gmaps_distance_km"] / p["length_km"]
        print(f"{p['surface_class']:<10s} {p['highway']:<10s} "
              f"{p['length_km']:>8.1f} {r['gmaps_distance_km']:>8.1f} "
              f"{r['gmaps_duration_hr']:>6.2f} {r['gmaps_speed_kmh']:>8.1f} {match:>7.2f}x")
        results.append({**p.to_dict(), **r, "length_match": match})
        time.sleep(0.1)

    if not results:
        print("No successful queries.")
        return

    df = pd.DataFrame(results)
    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)

    # Only use cases where Google route matches OSM length (0.7x–1.3x)
    df["same_road"] = (df["length_match"] >= 0.7) & (df["length_match"] <= 1.3)

    for s in ["paved", "unpaved"]:
        sub = df[df["surface_class"] == s]
        same = sub[sub["same_road"]]
        print(f"\n  {s.upper()} ({len(sub)} queries):")
        print(f"    Length match 0.7–1.3x: {len(same)} / {len(sub)}")
        if len(same) > 0:
            print(f"    Mean speed (same-road only): {same['gmaps_speed_kmh'].mean():.1f} km/h "
                  f"(range {same['gmaps_speed_kmh'].min():.1f}–{same['gmaps_speed_kmh'].max():.1f})")
        if len(sub) > 0:
            print(f"    Mean speed (all):            {sub['gmaps_speed_kmh'].mean():.1f} km/h")

    # Overall comparison
    same_paved = df[(df.surface_class == "paved") & df.same_road]
    same_unpaved = df[(df.surface_class == "unpaved") & df.same_road]
    if len(same_paved) > 0 and len(same_unpaved) > 0:
        ratio = same_paved.gmaps_speed_kmh.mean() / same_unpaved.gmaps_speed_kmh.mean()
        print(f"\n  Paved/unpaved speed ratio (same-road): {ratio:.2f}x")
        if ratio > 1.5:
            print("  ✓ Strong signal — proceed to larger pilot")
        elif ratio > 1.1:
            print("  ~ Weak signal — proceed carefully")
        else:
            print("  ✗ No signal — Google not differentiating by surface in TRAFFIC_UNAWARE")

    out = "outputs/gmaps_test_v3_results.csv"
    os.makedirs("outputs", exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
