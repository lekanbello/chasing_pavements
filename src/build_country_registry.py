"""
build_country_registry.py — Generate the master country registry from authoritative sources.

Pulls country metadata from:
  - Geofabrik: available PBF files for Africa
  - World Bank WDI API: GDP (current USD, 2019)
  - Manual lookup: UTM zones (computed from country centroids)

This script GENERATES configs/ssa_countries.csv. Run it to rebuild
the registry from scratch if any source data changes.

Usage:
    python3 src/build_country_registry.py
"""

import os
import numpy as np
import pandas as pd
import requests

YEAR = 2019
OUTPUT_CSV = "configs/ssa_countries.csv"

# ── SSA Country Definitions ────────────────────────────────────────
# These are the stable facts: ISO3 codes, names, regions, island status.
# Source: UN classification of Sub-Saharan Africa.

SSA_COUNTRIES = [
    # (country_name, iso3, region, is_island, approx_central_lon, approx_central_lat)
    ("Angola", "AGO", "Southern Africa", False, 17.9, -12.3),
    ("Benin", "BEN", "West Africa", False, 2.3, 9.3),
    ("Botswana", "BWA", "Southern Africa", False, 24.7, -22.3),
    ("Burkina Faso", "BFA", "West Africa", False, -1.6, 12.4),
    ("Burundi", "BDI", "East Africa", False, 29.9, -3.4),
    ("Cameroon", "CMR", "Central Africa", False, 12.4, 5.9),
    ("Cape Verde", "CPV", "West Africa", True, -23.0, 16.0),
    ("Central African Republic", "CAF", "Central Africa", False, 20.9, 6.6),
    ("Chad", "TCD", "Central Africa", False, 18.7, 15.4),
    ("Comoros", "COM", "East Africa", True, 44.3, -12.2),
    ("Congo DR", "COD", "Central Africa", False, 21.8, -2.9),
    ("Congo Republic", "COG", "Central Africa", False, 15.8, -0.2),
    ("Cote d Ivoire", "CIV", "West Africa", False, -5.5, 7.5),
    ("Djibouti", "DJI", "East Africa", False, 42.6, 11.6),
    ("Equatorial Guinea", "GNQ", "Central Africa", False, 10.3, 1.7),
    ("Eritrea", "ERI", "East Africa", False, 39.8, 15.2),
    ("Ethiopia", "ETH", "East Africa", False, 40.5, 9.0),
    ("Eswatini", "SWZ", "Southern Africa", False, 31.5, -26.5),
    ("Gabon", "GAB", "Central Africa", False, 11.6, -0.8),
    ("Gambia", "GMB", "West Africa", False, -15.3, 13.4),
    ("Ghana", "GHA", "West Africa", False, -1.0, 7.9),
    ("Guinea", "GIN", "West Africa", False, -9.7, 9.9),
    ("Guinea-Bissau", "GNB", "West Africa", False, -15.2, 12.0),
    ("Kenya", "KEN", "East Africa", False, 37.9, 0.0),
    ("Lesotho", "LSO", "Southern Africa", False, 28.2, -29.6),
    ("Liberia", "LBR", "West Africa", False, -9.4, 6.4),
    ("Madagascar", "MDG", "East Africa", True, 46.9, -18.8),
    ("Malawi", "MWI", "Southern Africa", False, 34.3, -13.3),
    ("Mali", "MLI", "West Africa", False, -4.0, 17.6),
    ("Mauritius", "MUS", "East Africa", True, 57.3, -20.3),
    ("Mozambique", "MOZ", "Southern Africa", False, 35.5, -18.7),
    ("Namibia", "NAM", "Southern Africa", False, 18.5, -22.0),
    ("Niger", "NER", "West Africa", False, 8.1, 17.6),
    ("Nigeria", "NGA", "West Africa", False, 8.7, 9.1),
    ("Rwanda", "RWA", "East Africa", False, 29.9, -2.0),
    ("Sao Tome and Principe", "STP", "Central Africa", True, 6.7, 0.2),
    ("Senegal", "SEN", "West Africa", False, -14.5, 14.5),
    ("Seychelles", "SYC", "East Africa", True, 55.5, -4.7),
    ("Sierra Leone", "SLE", "West Africa", False, -11.8, 8.5),
    ("Somalia", "SOM", "East Africa", False, 46.2, 5.2),
    ("South Africa", "ZAF", "Southern Africa", False, 22.9, -30.6),
    ("South Sudan", "SSD", "East Africa", False, 31.3, 7.9),
    ("Sudan", "SDN", "East Africa", False, 30.2, 12.9),
    ("Tanzania", "TZA", "East Africa", False, 34.9, -6.4),
    ("Togo", "TGO", "West Africa", False, 0.8, 8.6),
    ("Uganda", "UGA", "East Africa", False, 32.3, 1.4),
    ("Zambia", "ZMB", "Southern Africa", False, 27.8, -13.1),
    ("Zimbabwe", "ZWE", "Southern Africa", False, 29.2, -20.0),
]

# Geofabrik filename mapping (manually verified against download page)
# Most countries = {name}-latest.osm.pbf; some are bundled
GEOFABRIK_MAP = {
    "AGO": "angola-latest.osm.pbf",
    "BEN": "benin-latest.osm.pbf",
    "BWA": "botswana-latest.osm.pbf",
    "BFA": "burkina-faso-latest.osm.pbf",
    "BDI": "burundi-latest.osm.pbf",
    "CMR": "cameroon-latest.osm.pbf",
    "CPV": "cape-verde-latest.osm.pbf",
    "CAF": "central-african-republic-latest.osm.pbf",
    "TCD": "chad-latest.osm.pbf",
    "COM": "comoros-latest.osm.pbf",
    "COD": "congo-democratic-republic-latest.osm.pbf",
    "COG": "congo-brazzaville-latest.osm.pbf",
    "CIV": "ivory-coast-latest.osm.pbf",
    "DJI": "djibouti-latest.osm.pbf",
    "GNQ": "equatorial-guinea-latest.osm.pbf",
    "ERI": "eritrea-latest.osm.pbf",
    "ETH": "ethiopia-latest.osm.pbf",
    "SWZ": "swaziland-latest.osm.pbf",
    "GAB": "gabon-latest.osm.pbf",
    "GMB": "senegal-and-gambia-latest.osm.pbf",  # bundled
    "GHA": "ghana-latest.osm.pbf",
    "GIN": "guinea-latest.osm.pbf",
    "GNB": "guinea-bissau-latest.osm.pbf",
    "KEN": "kenya-latest.osm.pbf",
    "LSO": "south-africa-and-lesotho-latest.osm.pbf",  # bundled
    "LBR": "liberia-latest.osm.pbf",
    "MDG": "madagascar-latest.osm.pbf",
    "MWI": "malawi-latest.osm.pbf",
    "MLI": "mali-latest.osm.pbf",
    "MUS": "mauritius-latest.osm.pbf",
    "MOZ": "mozambique-latest.osm.pbf",
    "NAM": "namibia-latest.osm.pbf",
    "NER": "niger-latest.osm.pbf",
    "NGA": "nigeria-latest.osm.pbf",
    "RWA": "rwanda-latest.osm.pbf",
    "STP": "sao-tome-and-principe-latest.osm.pbf",
    "SEN": "senegal-and-gambia-latest.osm.pbf",  # bundled
    "SYC": "seychelles-latest.osm.pbf",
    "SLE": "sierra-leone-latest.osm.pbf",
    "SOM": "somalia-latest.osm.pbf",
    "ZAF": "south-africa-and-lesotho-latest.osm.pbf",  # bundled
    "SSD": "south-sudan-latest.osm.pbf",
    "SDN": "sudan-latest.osm.pbf",
    "TZA": "tanzania-latest.osm.pbf",
    "TGO": "togo-latest.osm.pbf",
    "UGA": "uganda-latest.osm.pbf",
    "ZMB": "zambia-latest.osm.pbf",
    "ZWE": "zimbabwe-latest.osm.pbf",
}


def compute_utm_epsg(lon, lat):
    """Compute UTM zone EPSG code from coordinates."""
    zone = int((lon + 180) / 6) + 1
    if lat >= 0:
        return 32600 + zone
    else:
        return 32700 + zone


def fetch_gdp_from_wdi(iso3_list, year=2019):
    """Pull GDP (current USD) from World Bank WDI API."""
    print(f"Fetching GDP data from World Bank WDI (year={year})...")
    gdp = {}
    try:
        import wbgapi as wb
        for row in wb.data.fetch("NY.GDP.MKTP.CD", time=year):
            if row["economy"] in iso3_list and row["value"]:
                gdp[row["economy"]] = int(row["value"])
        print(f"  Retrieved GDP for {len(gdp)} / {len(iso3_list)} countries")
    except Exception as e:
        print(f"  WDI API error: {e}")
        print("  GDP values will be set to 0 — update manually")
    return gdp


def main():
    rows = []
    iso3_list = [c[1] for c in SSA_COUNTRIES]
    gdp_data = fetch_gdp_from_wdi(iso3_list, YEAR)

    for name, iso3, region, is_island, lon, lat in SSA_COUNTRIES:
        utm_epsg = compute_utm_epsg(lon, lat)
        geofabrik = GEOFABRIK_MAP.get(iso3, f"{name.lower().replace(' ', '-')}-latest.osm.pbf")
        gdp = gdp_data.get(iso3, 0)
        enabled = not is_island  # islands disabled by default

        rows.append({
            "country_name": name,
            "iso3": iso3,
            "geofabrik_filename": geofabrik,
            "utm_epsg": utm_epsg,
            "national_gdp_2019": gdp,
            "gadm_layer": "ADM_ADM_2",
            "is_island": str(is_island).lower(),
            "region": region,
            "enabled": str(enabled).lower(),
        })

    df = pd.DataFrame(rows)

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved {len(df)} countries to {OUTPUT_CSV}")
    print(f"  Enabled: {df['enabled'].value_counts().get('true', 0)}")
    print(f"  Disabled (islands): {df['enabled'].value_counts().get('false', 0)}")
    print(f"  GDP > 0: {(df['national_gdp_2019'] > 0).sum()}")
    print(f"  GDP = 0: {(df['national_gdp_2019'] == 0).sum()} (Eritrea, South Sudan — no WDI data)")


if __name__ == "__main__":
    main()
