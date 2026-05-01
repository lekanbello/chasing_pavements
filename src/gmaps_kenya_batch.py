"""
gmaps_kenya_batch.py — Run a Kenya batch parallel to the Tanzania batch
to validate that the paved/unpaved speed gap holds across countries.

Output: outputs/gmaps_kenya_queries.csv
"""

import os, time
import numpy as np
import pandas as pd
import geopandas as gpd
import requests

API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
ROAD_CLASSES = {"trunk", "primary", "secondary"}
MIN_LEN = 10
MAX_LEN = 50
N_PER_SURFACE = 8


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


def select_segments(country_gpkg):
    print(f"Loading {country_gpkg}...")
    gdf = gpd.read_file(country_gpkg)
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
                "name": r.get("name", ""),
                "length_km": r["length_km"],
                "o_lon": start[0], "o_lat": start[1],
                "d_lon": end[0], "d_lat": end[1],
            })
        except Exception:
            continue
    df = pd.DataFrame(rows)

    np.random.seed(7)
    class_order = ["trunk", "primary", "secondary"]
    picks = []
    for surf in ["paved", "unpaved"]:
        sub = df[df.surface_class == surf].copy()
        sub["class_rank"] = sub["highway"].map({c: i for i, c in enumerate(class_order)})
        sub = sub.sort_values(["class_rank", "length_km"], ascending=[True, False])
        picks.append(sub.head(N_PER_SURFACE))
    return pd.concat(picks, ignore_index=True)


def main():
    api_key = load_api_key()
    print(f"API key loaded: {api_key[:6]}...{api_key[-4:]}\n")

    pairs = select_segments("data/processed/kenya_roads.gpkg")
    print(f"\nSelected {len(pairs)} Kenya segments.\n")

    print("Querying Google Maps (Kenya)...\n")
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
        results.append({**p.to_dict(), **r, "length_match": match, "country": "Kenya"})
        time.sleep(0.1)

    if not results:
        print("No successful queries.")
        return
    df = pd.DataFrame(results)
    df["same_road"] = (df["length_match"] >= 0.7) & (df["length_match"] <= 1.3)

    print("\nSUMMARY (same-road queries only)")
    for s in ["paved", "unpaved"]:
        sub = df[(df.surface_class == s) & df.same_road]
        if len(sub) > 0:
            print(f"  {s.upper()}: n={len(sub)}, mean={sub.gmaps_speed_kmh.mean():.1f} km/h")

    same_p = df[(df.surface_class == "paved") & df.same_road]
    same_u = df[(df.surface_class == "unpaved") & df.same_road]
    if len(same_p) > 0 and len(same_u) > 0:
        ratio = same_p.gmaps_speed_kmh.mean() / same_u.gmaps_speed_kmh.mean()
        print(f"  Paved/unpaved ratio: {ratio:.2f}x")

    csv_out = "outputs/gmaps_kenya_queries.csv"
    df.to_csv(csv_out, index=False)
    print(f"\nSaved: {csv_out}")


if __name__ == "__main__":
    main()
