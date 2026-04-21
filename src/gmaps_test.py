"""
gmaps_test.py — Minimal test of Google Maps Routes API.

Step 1: Single query to verify the API key works.
Step 2: 10-pair paved vs unpaved comparison in Tanzania.

Usage:
    python3 src/gmaps_test.py --check    # single query, 1 element
    python3 src/gmaps_test.py --compare  # 10-pair paved/unpaved test, 10 elements

Reads GOOGLE_MAPS_API_KEY from .env or environment.
"""

import os
import sys
import json
import argparse
import time
import requests
import pandas as pd


API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def load_api_key():
    """Load API key from .env file or environment variable."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if key:
        return key
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith("GOOGLE_MAPS_API_KEY="):
                    return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("GOOGLE_MAPS_API_KEY not found in .env or environment")


def query_route(origin_lat, origin_lon, dest_lat, dest_lon, api_key, timeout=30):
    """
    Query Google Maps Routes API for a single OD pair.

    Uses TRAFFIC_UNAWARE (Essentials tier, no traffic model, 1 element cost).
    Returns distance (meters) and duration (seconds).
    """
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline",
    }
    body = {
        "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lon}}},
        "destination": {"location": {"latLng": {"latitude": dest_lat, "longitude": dest_lon}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_UNAWARE",
    }

    r = requests.post(API_URL, headers=headers, json=body, timeout=timeout)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}

    data = r.json()
    if "routes" not in data or not data["routes"]:
        return {"error": "No route found", "raw": data}

    route = data["routes"][0]
    # duration is a string like "12345s"
    dur_str = route.get("duration", "0s")
    duration_sec = float(dur_str.rstrip("s"))
    distance_m = route.get("distanceMeters", 0)

    return {
        "distance_km": distance_m / 1000,
        "duration_min": duration_sec / 60,
        "duration_hr": duration_sec / 3600,
        "speed_kmh": (distance_m / 1000) / (duration_sec / 3600) if duration_sec > 0 else None,
    }


def cmd_check(api_key):
    """Single test query. Uses 1 API element."""
    # Dar es Salaam → Morogoro (should be ~200 km on paved A7 highway)
    print("Test query: Dar es Salaam → Morogoro (paved A7 highway)")
    print("-" * 60)

    result = query_route(
        origin_lat=-6.7924, origin_lon=39.2083,   # Dar es Salaam
        dest_lat=-6.8278,  dest_lon=37.6591,      # Morogoro
        api_key=api_key,
    )

    if "error" in result:
        print(f"FAILED: {result['error']}")
        return False

    print(f"  Distance: {result['distance_km']:.1f} km")
    print(f"  Duration: {result['duration_hr']:.2f} h ({result['duration_min']:.0f} min)")
    print(f"  Speed:    {result['speed_kmh']:.1f} km/h")
    print(f"\nAPI works ✓")
    print(f"(Speed ~70-90 km/h expected for this paved highway.)")
    return True


def cmd_compare(api_key):
    """10-pair paved vs unpaved comparison. Uses 10 API elements."""
    # 5 expected-paved routes (Tanzania major highways, between district centroids)
    # 5 expected-unpaved routes (between rural district centroids in western Tanzania)

    pairs = [
        # --- PAVED routes (major cities on highways) ---
        {"label": "Dar es Salaam → Morogoro",    "surface": "paved",
         "o_lat": -6.7924, "o_lon": 39.2083, "d_lat": -6.8278, "d_lon": 37.6591},
        {"label": "Arusha → Moshi",              "surface": "paved",
         "o_lat": -3.3869, "o_lon": 36.6830, "d_lat": -3.3515, "d_lon": 37.3407},
        {"label": "Morogoro → Dodoma",           "surface": "paved",
         "o_lat": -6.8278, "o_lon": 37.6591, "d_lat": -6.1630, "d_lon": 35.7516},
        {"label": "Dar es Salaam → Chalinze",    "surface": "paved",
         "o_lat": -6.7924, "o_lon": 39.2083, "d_lat": -6.6406, "d_lon": 38.3506},
        {"label": "Mwanza → Musoma",             "surface": "paved",
         "o_lat": -2.5164, "o_lon": 32.9175, "d_lat": -1.5010, "d_lon": 33.8031},

        # --- UNPAVED routes (rural district pairs in western Tanzania) ---
        {"label": "Tabora → Kigoma",             "surface": "unpaved",
         "o_lat": -5.0167, "o_lon": 32.8000, "d_lat": -4.8786, "d_lon": 29.6262},
        {"label": "Sumbawanga → Mpanda",         "surface": "unpaved",
         "o_lat": -7.9700, "o_lon": 31.6200, "d_lat": -6.3442, "d_lon": 31.0697},
        {"label": "Singida → Manyoni",           "surface": "unpaved",
         "o_lat": -4.8167, "o_lon": 34.7500, "d_lat": -5.7547, "d_lon": 34.8278},
        {"label": "Tunduru → Songea",            "surface": "unpaved",
         "o_lat": -11.1089, "o_lon": 37.3594, "d_lat": -10.6848, "d_lon": 35.6500},
        {"label": "Masasi → Tunduru",            "surface": "unpaved",
         "o_lat": -10.7350, "o_lon": 38.8017, "d_lat": -11.1089, "d_lon": 37.3594},
    ]

    print(f"\nQuerying {len(pairs)} routes in Tanzania...\n")
    print(f"{'Route':<32s} {'Surf.':<8s} {'Dist (km)':>10s} {'Time (h)':>10s} {'Speed (km/h)':>14s}")
    print("-" * 76)

    results = []
    for p in pairs:
        r = query_route(p["o_lat"], p["o_lon"], p["d_lat"], p["d_lon"], api_key)
        if "error" in r:
            print(f"{p['label']:<32s} ERROR: {r['error']}")
            continue

        print(f"{p['label']:<32s} {p['surface']:<8s} "
              f"{r['distance_km']:>10.1f} {r['duration_hr']:>10.2f} {r['speed_kmh']:>14.1f}")

        results.append({
            "label": p["label"],
            "surface": p["surface"],
            "distance_km": r["distance_km"],
            "duration_hr": r["duration_hr"],
            "speed_kmh": r["speed_kmh"],
        })
        time.sleep(0.1)  # be polite

    if not results:
        print("\nNo successful queries.")
        return

    df = pd.DataFrame(results)
    print("\n" + "=" * 76)
    print("SUMMARY")
    print("=" * 76)
    for s in ["paved", "unpaved"]:
        sub = df[df["surface"] == s]
        if len(sub) > 0:
            print(f"  Expected {s:7s}: {len(sub)} routes, "
                  f"mean speed = {sub['speed_kmh'].mean():.1f} km/h "
                  f"(range {sub['speed_kmh'].min():.1f}–{sub['speed_kmh'].max():.1f})")

    if {"paved", "unpaved"}.issubset(set(df["surface"])):
        ratio = df[df.surface == "paved"].speed_kmh.mean() / df[df.surface == "unpaved"].speed_kmh.mean()
        print(f"\n  Paved/unpaved speed ratio: {ratio:.2f}x")
        print(f"  Implied cost ratio c = (unpaved km equivalent to 1 paved km) = {ratio:.2f}")
        if ratio > 1.5:
            print(f"\n  ✓ Strong signal — paved routes are substantially faster. Proceed to full pilot.")
        elif ratio > 1.1:
            print(f"\n  ~ Weak signal — some difference but small. Inspect before scaling.")
        else:
            print(f"\n  ✗ No signal — Google is not picking up the surface difference. Rethink.")

    out = "outputs/gmaps_test_results.csv"
    os.makedirs("outputs", exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nSaved: {out}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Single-query test (1 element)")
    parser.add_argument("--compare", action="store_true", help="10-pair paved/unpaved test (10 elements)")
    args = parser.parse_args()

    if not (args.check or args.compare):
        parser.print_help()
        return

    api_key = load_api_key()
    masked = api_key[:6] + "..." + api_key[-4:]
    print(f"API key loaded: {masked}")

    if args.check:
        cmd_check(api_key)

    if args.compare:
        cmd_compare(api_key)


if __name__ == "__main__":
    main()
