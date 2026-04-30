"""
country_config.py — Load country configurations from master CSV registry.

Single source of truth for all country metadata. Generates config dicts
compatible with run_country.py from CSV rows.
"""

import os
import pandas as pd

MASTER_CSV = os.path.join(os.path.dirname(__file__), "..", "configs", "ssa_countries.csv")
YEAR = 2019

# Default model parameters (R&RH 2017 Krugman-CES; trade elasticity = σ-1).
DEFAULT_PARAMS = {
    "sigma": 5.0,
    "kappa": 2.0,
    "alpha": 0.65,
}


def load_registry(csv_path=None):
    """Load the master country registry as a DataFrame."""
    path = csv_path or MASTER_CSV
    df = pd.read_csv(path)
    df["enabled"] = df["enabled"].astype(str).str.lower() == "true"
    return df


def get_enabled_countries(csv_path=None):
    """Return DataFrame of enabled countries only."""
    return load_registry(csv_path).query("enabled").reset_index(drop=True)


def build_config(row):
    """Build a config dict compatible with run_country.py from a registry row."""
    iso = row["iso3"]
    iso_lower = iso.lower()
    name_lower = row["country_name"].lower().replace(" ", "_").replace("'", "")

    return {
        "country_name": row["country_name"],
        "iso3": iso,
        "year": YEAR,
        # Input paths + download URLs
        "osm_pbf": f"data/raw/{row['geofabrik_filename']}",
        "osm_pbf_url": f"https://download.geofabrik.de/africa/{row['geofabrik_filename']}",
        "gadm_gpkg": f"data/raw/gadm41_{iso}.gpkg",
        "gadm_gpkg_url": f"https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_{iso}.gpkg",
        "gadm_layer": row.get("gadm_layer", "ADM_ADM_2"),
        "worldpop_path": f"data/raw/{iso_lower}_ppp_{YEAR}.tif",
        "worldpop_url": f"https://data.worldpop.org/GIS/Population/Global_2000_2020/{YEAR}/{iso}/{iso_lower}_ppp_{YEAR}.tif",
        # Spatial
        "utm_epsg": int(row["utm_epsg"]),
        # Output paths
        "roads_gpkg": f"data/processed/{name_lower}_roads.gpkg",
        "admin_gpkg": f"data/processed/{name_lower}_admin2.gpkg",
        "trade_costs_baseline": f"data/processed/{name_lower}_trade_costs_baseline.npy",
        "trade_costs_counterfactual": f"data/processed/{name_lower}_trade_costs_counterfactual.npy",
        "admin_names": f"data/processed/{name_lower}_admin2_names.npy",
        "calibrated_gpkg": f"data/processed/{name_lower}_calibrated.gpkg",
        "trade_shares": f"data/processed/{name_lower}_baseline_trade_shares.npy",
        "model_params": f"data/processed/{name_lower}_model_params.json",
        "counterfactual_gpkg": f"data/processed/{name_lower}_counterfactual.gpkg",
        "counterfactual_results": f"data/processed/{name_lower}_counterfactual_results.json",
        "run_status": f"data/processed/{name_lower}_run_status.json",
        # GDP
        "national_gdp_fallback": float(row["national_gdp_2019"]),
        # Parameters
        "parameters": DEFAULT_PARAMS.copy(),
        # Cost multipliers
        "cost_paved": 1.0,
        "cost_unpaved": 3.0,
        "cost_unknown": 2.0,
    }


def get_config_by_iso3(iso3, csv_path=None):
    """Look up a country by ISO3 code and return its config dict."""
    df = load_registry(csv_path)
    match = df[df["iso3"] == iso3.upper()]
    if len(match) == 0:
        available = ", ".join(sorted(df["iso3"].tolist()))
        raise ValueError(f"Country {iso3} not found. Available: {available}")
    return build_config(match.iloc[0])


def get_configs_by_iso3_list(iso3_list, csv_path=None):
    """Return configs for a list of ISO3 codes."""
    return [get_config_by_iso3(iso, csv_path) for iso in iso3_list]


def get_configs_by_region(region, csv_path=None):
    """Return configs for all enabled countries in a region."""
    df = get_enabled_countries(csv_path)
    matches = df[df["region"].str.contains(region, case=False, na=False)]
    return [build_config(row) for _, row in matches.iterrows()]


def get_geofabrik_downloads(csv_path=None):
    """Return deduplicated list of Geofabrik files to download."""
    df = get_enabled_countries(csv_path)
    unique = df.drop_duplicates(subset="geofabrik_filename")
    return [
        {"filename": row["geofabrik_filename"],
         "url": f"https://download.geofabrik.de/africa/{row['geofabrik_filename']}"}
        for _, row in unique.iterrows()
    ]
