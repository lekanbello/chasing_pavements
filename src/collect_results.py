"""
collect_results.py — Aggregate per-country results into summary CSVs.

Reads all *_counterfactual_results.json and *_model_params.json files
and produces:
  - outputs/ssa_model_results.csv (welfare gains for all countries)
  - outputs/ssa_data_summary.csv (road stats, if available)

Usage:
    python3 src/collect_results.py
"""

import os
import json
import glob
import pandas as pd
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from country_config import load_registry, build_config

PROCESSED_DIR = "data/processed"
OUTPUT_DIR = "outputs"


def collect_model_results():
    """Collect counterfactual results from all countries."""
    registry = load_registry()
    rows = []

    for _, country in registry.iterrows():
        cfg = build_config(country)
        iso3 = country["iso3"]
        name = country["country_name"]

        # Counterfactual results
        cf_path = cfg["counterfactual_results"]
        params_path = cfg["model_params"]

        if os.path.exists(cf_path):
            with open(cf_path) as f:
                cf = json.load(f)

            params = {}
            if os.path.exists(params_path):
                with open(params_path) as f:
                    params = json.load(f)

            rows.append({
                "country_name": name,
                "iso3": iso3,
                "region": country["region"],
                "national_gdp_2019": country["national_gdp_2019"],
                "n_districts": cf.get("n_districts", cf.get("n_total", "")),
                "welfare_pct": cf.get("welfare_pct", ""),
                "welfare_s1_pct": cf.get("welfare_s1_pct", ""),
                "median_pi_nn": params.get("median_pi_nn", ""),
                "trade_cost_scale": params.get("trade_cost_scale", ""),
                "total_population": params.get("total_population", ""),
                "status": "success",
            })
        else:
            # Check for run status
            status_path = cfg.get("run_status", "")
            error = ""
            if os.path.exists(status_path):
                with open(status_path) as f:
                    status = json.load(f)
                error = status.get("error", "")

            rows.append({
                "country_name": name,
                "iso3": iso3,
                "region": country["region"],
                "national_gdp_2019": country["national_gdp_2019"],
                "status": "missing" if not error else "failed",
                "error": error,
            })

    df = pd.DataFrame(rows)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "ssa_model_results.csv")
    df.to_csv(out_path, index=False)

    # Print summary
    success = df[df["status"] == "success"]
    print(f"\n{'='*60}")
    print(f"SSA MODEL RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Countries with results: {len(success)} / {len(df)}")

    if len(success) > 0:
        print(f"\n{'Country':<25s} {'Region':<18s} {'Welfare':>10s} {'Districts':>10s}")
        print(f"{'-'*65}")
        for _, row in success.sort_values("welfare_pct", ascending=False).iterrows():
            w = row.get("welfare_pct", "")
            w_str = f"{w:+.1f}%" if isinstance(w, (int, float)) else str(w)
            print(f"{row['country_name']:<25s} {row['region']:<18s} {w_str:>10s} {row.get('n_districts',''):>10}")

    missing = df[df["status"] != "success"]
    if len(missing) > 0:
        print(f"\nMissing/failed ({len(missing)}):")
        for _, row in missing.iterrows():
            print(f"  {row['iso3']} {row['country_name']}: {row['status']}")

    print(f"\nSaved to {out_path}")
    return df


def collect_data_summary():
    """Collect road data summaries from model params files."""
    registry = load_registry()
    rows = []

    for _, country in registry.iterrows():
        cfg = build_config(country)
        params_path = cfg["model_params"]

        if os.path.exists(params_path):
            with open(params_path) as f:
                params = json.load(f)

            rows.append({
                "country_name": country["country_name"],
                "iso3": country["iso3"],
                "region": country["region"],
                "n_districts": params.get("n_districts", ""),
                "total_population": params.get("total_population", ""),
                "national_gdp": params.get("national_gdp_usd", ""),
                "trade_cost_scale": params.get("trade_cost_scale", ""),
                "median_pi_nn": params.get("median_pi_nn", ""),
            })

    if rows:
        df = pd.DataFrame(rows)
        out_path = os.path.join(OUTPUT_DIR, "ssa_data_summary.csv")
        df.to_csv(out_path, index=False)
        print(f"Data summary: {len(df)} countries → {out_path}")
        return df
    return None


def main():
    collect_model_results()
    collect_data_summary()


if __name__ == "__main__":
    main()
