"""
gmaps_test_v2.py — Paved vs unpaved Google Maps test using ACTUAL data.

Picks OD pairs from the Tanzania pipeline output where we know — from our own
road network analysis — whether the shortest path is mostly paved or unpaved.
Then queries Google Maps and checks whether travel speeds differ.

Uses tc_cf/tc_base as a proxy for paved share of the route:
  - ratio ~ 1.0  → route is already mostly paved
  - ratio ~ 0.4  → route is mostly unpaved (baseline with c=3, cf with c=1)

Usage:
    python3 src/gmaps_test_v2.py  # ~10 API elements
"""

import os
import time
import numpy as np
import pandas as pd
import geopandas as gpd
import requests


API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


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
        "distance_km": dist_m / 1000,
        "duration_hr": dur_s / 3600,
        "speed_kmh": (dist_m / 1000) / (dur_s / 3600) if dur_s > 0 else None,
    }


def select_test_pairs():
    """
    Select OD pairs using Tanzania data: 5 mostly-paved, 5 mostly-unpaved.
    """
    admin = gpd.read_file("data/processed/tanzania_calibrated.gpkg")
    tc_base = np.load("data/processed/tanzania_trade_costs_baseline.npy")
    tc_cf = np.load("data/processed/tanzania_trade_costs_counterfactual.npy")

    n = len(admin)
    conn = np.isfinite(tc_base) & np.isfinite(tc_cf) & (tc_base > 0) & (tc_cf > 0)
    np.fill_diagonal(conn, False)

    # Ratio: tc_cf / tc_base.  ~1 = already paved; lower = more unpaved content
    ratio = np.full((n, n), np.nan)
    ratio[conn] = tc_cf[conn] / tc_base[conn]

    # Distance filter: want routes 100–400 km (short enough to be meaningful,
    # long enough that surface composition matters)
    dist_ok = (tc_cf >= 100) & (tc_cf <= 400)
    mask = conn & dist_ok & np.isfinite(ratio)

    # Get candidate pairs
    i_idx, j_idx = np.where(mask & (np.arange(n)[:, None] < np.arange(n)[None, :]))
    cand = pd.DataFrame({
        "i": i_idx, "j": j_idx,
        "ratio": ratio[i_idx, j_idx],
        "cf_km": tc_cf[i_idx, j_idx],
    })

    # For paved pairs: pick ratio closest to 1
    cand_paved = cand.sort_values("ratio", ascending=False).head(30)

    # For unpaved pairs: pick lowest ratio (most unpaved content)
    cand_unpaved = cand.sort_values("ratio", ascending=True).head(30)

    # Sample 5 from each, ensuring no repeat districts
    np.random.seed(42)
    picks = []

    used_districts = set()
    for _, row in cand_paved.iterrows():
        if len(picks) >= 5:
            break
        if row["i"] in used_districts or row["j"] in used_districts:
            continue
        picks.append({**row.to_dict(), "expected": "paved"})
        used_districts.update([row["i"], row["j"]])

    used_districts = set()
    for _, row in cand_unpaved.iterrows():
        n_unpaved = sum(1 for p in picks if p["expected"] == "unpaved")
        if n_unpaved >= 5:
            break
        if row["i"] in used_districts or row["j"] in used_districts:
            continue
        picks.append({**row.to_dict(), "expected": "unpaved"})
        used_districts.update([row["i"], row["j"]])

    # Enrich with names and coordinates
    out = []
    for p in picks:
        i, j = int(p["i"]), int(p["j"])
        out.append({
            "origin_name": admin.iloc[i]["NAME_2"],
            "dest_name": admin.iloc[j]["NAME_2"],
            "origin_region": admin.iloc[i]["NAME_1"],
            "dest_region": admin.iloc[j]["NAME_1"],
            "o_lat": admin.iloc[i]["centroid_lat"],
            "o_lon": admin.iloc[i]["centroid_lon"],
            "d_lat": admin.iloc[j]["centroid_lat"],
            "d_lon": admin.iloc[j]["centroid_lon"],
            "cf_base_ratio": p["ratio"],
            "cf_km": p["cf_km"],
            "expected_surface": p["expected"],
        })
    return out


def main():
    api_key = load_api_key()
    masked = api_key[:6] + "..." + api_key[-4:]
    print(f"API key loaded: {masked}\n")

    pairs = select_test_pairs()

    print("Selected pairs from Tanzania data:")
    print(f"{'Origin':<22s} {'→ Destination':<22s} {'Surface':<10s} {'cf/base':>8s} {'cf_km':>8s}")
    print("-" * 76)
    for p in pairs:
        print(f"{p['origin_name']:<22s} → {p['dest_name']:<20s} "
              f"{p['expected_surface']:<10s} {p['cf_base_ratio']:>8.3f} {p['cf_km']:>8.0f}")

    print("\nQuerying Google Maps...\n")
    print(f"{'Origin → Dest':<44s} {'Expect':<10s} {'Dist':>8s} {'Hr':>6s} {'km/h':>8s}")
    print("-" * 76)

    results = []
    for p in pairs:
        r = query_route(p["o_lat"], p["o_lon"], p["d_lat"], p["d_lon"], api_key)
        label = f"{p['origin_name']} → {p['dest_name']}"
        if "error" in r:
            print(f"{label:<44s} ERROR: {r['error']}")
            continue
        print(f"{label:<44s} {p['expected_surface']:<10s} "
              f"{r['distance_km']:>8.1f} {r['duration_hr']:>6.2f} {r['speed_kmh']:>8.1f}")
        results.append({**p, **r})
        time.sleep(0.1)

    if not results:
        print("No successful queries.")
        return

    df = pd.DataFrame(results)
    print("\n" + "=" * 76)
    print("SUMMARY")
    print("=" * 76)
    for s in ["paved", "unpaved"]:
        sub = df[df["expected_surface"] == s]
        if len(sub) > 0:
            print(f"  Expected {s:7s} ({len(sub)} routes):")
            print(f"    Mean Google distance: {sub['distance_km'].mean():.0f} km")
            print(f"    Mean speed:           {sub['speed_kmh'].mean():.1f} km/h (range {sub['speed_kmh'].min():.1f}–{sub['speed_kmh'].max():.1f})")
            print(f"    Mean cf/base ratio:   {sub['cf_base_ratio'].mean():.3f}")

    if set(df["expected_surface"]) >= {"paved", "unpaved"}:
        paved_speed = df[df.expected_surface == "paved"].speed_kmh.mean()
        unpaved_speed = df[df.expected_surface == "unpaved"].speed_kmh.mean()
        ratio = paved_speed / unpaved_speed
        print(f"\n  Paved/unpaved speed ratio: {ratio:.2f}x")
        if ratio > 1.5:
            print("  ✓ Strong signal — proceed to larger pilot")
        elif ratio > 1.1:
            print("  ~ Weak signal — inspect routes")
        else:
            print("  ✗ No signal — Google not differentiating by surface")

    out = "outputs/gmaps_test_v2_results.csv"
    os.makedirs("outputs", exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
