"""
gmaps_test_v4.py — Replication and generalization of the v3 paved/unpaved test.

Uses a different random seed and a larger sample to check whether the 1.39x
speed ratio from v3 is robust. Also adds primary and secondary road classes
to test whether the signal holds beyond trunk roads.

Usage:
    python3 src/gmaps_test_v4.py  # ~30 API elements
"""

import os
import time
import numpy as np
import pandas as pd
import geopandas as gpd
import requests


API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
MIN_LEN = 10
MAX_LEN = 50


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


def endpoints(geom):
    coords = list(geom.coords) if geom.geom_type == "LineString" else list(geom.geoms[0].coords)
    return coords[0], coords[-1]


def select_segments(gdf, road_class, n_paved, n_unpaved, exclude_ids=None, seed=43):
    """Pick random segments from a given road class, excluding previously used ones."""
    exclude_ids = exclude_ids or set()
    rng = np.random.default_rng(seed)

    mask = (
        (gdf["highway"] == road_class)
        & gdf["surface_class"].isin({"paved", "unpaved"})
        & (gdf["length_km"] >= MIN_LEN)
        & (gdf["length_km"] <= MAX_LEN)
        & (~gdf["osm_id"].isin(exclude_ids))
    )
    filt = gdf[mask].copy()

    picks = []
    for surf, n in [("paved", n_paved), ("unpaved", n_unpaved)]:
        sub = filt[filt.surface_class == surf]
        if len(sub) == 0:
            continue
        sample = sub.sample(n=min(n, len(sub)), random_state=rng.integers(0, 1_000_000))
        for _, r in sample.iterrows():
            try:
                start, end = endpoints(r.geometry)
                picks.append({
                    "osm_id": r["osm_id"],
                    "highway": r["highway"],
                    "surface_class": r["surface_class"],
                    "length_km": r["length_km"],
                    "o_lon": start[0], "o_lat": start[1],
                    "d_lon": end[0], "d_lat": end[1],
                })
            except Exception:
                continue
    return picks


def main():
    api_key = load_api_key()
    masked = api_key[:6] + "..." + api_key[-4:]
    print(f"API key loaded: {masked}\n")

    print("Loading Tanzania OSM roads...")
    gdf = gpd.read_file("data/processed/tanzania_roads.gpkg")
    print(f"  Total segments: {len(gdf):,}\n")

    # Previously used osm_ids (from v3) — exclude them
    v3_path = "outputs/gmaps_test_v3_results.csv"
    exclude = set()
    if os.path.exists(v3_path):
        prev = pd.read_csv(v3_path)
        exclude = set(prev["osm_id"].astype(int).tolist())
        print(f"Excluding {len(exclude)} segments used in v3\n")

    # Three groups: trunk (replication), primary + secondary (generalization)
    picks = []
    picks += select_segments(gdf, "trunk", n_paved=10, n_unpaved=10, exclude_ids=exclude, seed=43)
    picks += select_segments(gdf, "primary", n_paved=5, n_unpaved=5, exclude_ids=exclude, seed=44)
    picks += select_segments(gdf, "secondary", n_paved=5, n_unpaved=5, exclude_ids=exclude, seed=45)

    print(f"Selected {len(picks)} segments:")
    from collections import Counter
    breakdown = Counter((p["highway"], p["surface_class"]) for p in picks)
    for (hw, sc), n in sorted(breakdown.items()):
        print(f"  {hw:<12s} {sc:<10s} {n}")

    print("\nQuerying Google Maps...\n")
    print(f"{'class':<12s} {'surface':<10s} {'len_km':>8s} {'gm_km':>8s} {'hr':>6s} {'km/h':>8s} {'match':>7s}")
    print("-" * 70)

    results = []
    for p in picks:
        r = query_route(p["o_lat"], p["o_lon"], p["d_lat"], p["d_lon"], api_key)
        if "error" in r:
            print(f"{p['highway']:<12s} {p['surface_class']:<10s} {p['length_km']:>8.1f}  ERROR: {r['error']}")
            continue
        match = r["gmaps_distance_km"] / p["length_km"]
        print(f"{p['highway']:<12s} {p['surface_class']:<10s} "
              f"{p['length_km']:>8.1f} {r['gmaps_distance_km']:>8.1f} "
              f"{r['gmaps_duration_hr']:>6.2f} {r['gmaps_speed_kmh']:>8.1f} {match:>7.2f}x")
        results.append({**p, **r, "length_match": match})
        time.sleep(0.1)

    if not results:
        print("No successful queries.")
        return

    df = pd.DataFrame(results)
    df["same_road"] = (df["length_match"] >= 0.7) & (df["length_match"] <= 1.3)

    print("\n" + "=" * 70)
    print("SUMMARY — replication of v3")
    print("=" * 70)

    print(f"\n  By road class (same-road queries only):")
    print(f"  {'class':<12s} {'surface':<10s} {'N':>4s} {'mean_kmh':>10s} {'range':>14s}")
    for hw in ["trunk", "primary", "secondary"]:
        for s in ["paved", "unpaved"]:
            sub = df[(df.highway == hw) & (df.surface_class == s) & df.same_road]
            if len(sub) > 0:
                print(f"  {hw:<12s} {s:<10s} {len(sub):>4d} "
                      f"{sub['gmaps_speed_kmh'].mean():>10.1f} "
                      f"{sub['gmaps_speed_kmh'].min():.1f}–{sub['gmaps_speed_kmh'].max():.1f}")

    # Overall ratios
    print(f"\n  Overall ratio (same-road only):")
    for hw in ["trunk", "primary", "secondary"]:
        p = df[(df.highway == hw) & (df.surface_class == "paved") & df.same_road]
        u = df[(df.highway == hw) & (df.surface_class == "unpaved") & df.same_road]
        if len(p) > 0 and len(u) > 0:
            ratio = p.gmaps_speed_kmh.mean() / u.gmaps_speed_kmh.mean()
            print(f"    {hw:<12s}: paved {p.gmaps_speed_kmh.mean():.1f} / unpaved {u.gmaps_speed_kmh.mean():.1f} = {ratio:.2f}x")

    all_p = df[(df.surface_class == "paved") & df.same_road]
    all_u = df[(df.surface_class == "unpaved") & df.same_road]
    if len(all_p) > 0 and len(all_u) > 0:
        ratio = all_p.gmaps_speed_kmh.mean() / all_u.gmaps_speed_kmh.mean()
        print(f"    {'ALL':<12s}: paved {all_p.gmaps_speed_kmh.mean():.1f} / unpaved {all_u.gmaps_speed_kmh.mean():.1f} = {ratio:.2f}x")

        print(f"\n  v3 ratio was 1.39x (trunk only, 5+5). v4 overall: {ratio:.2f}x")
        if 1.2 <= ratio <= 1.6:
            print("  ✓ Replicates — result is robust.")
        elif ratio > 1.1:
            print("  ~ Similar direction but different magnitude.")
        else:
            print("  ✗ Does not replicate.")

    out = "outputs/gmaps_test_v4_results.csv"
    os.makedirs("outputs", exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
