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
                # Stage 1 (κ=0, no mobility)
                "welfare_s1_pct": cf.get("welfare_s1_pct", ""),
                # Stage 2 (κ=∞, perfect mobility, headline)
                "welfare_pct": cf.get("welfare_pct", ""),
                "welfare_cv": cf.get("welfare_cv", ""),
                # Welfare equalization diagnostic (was misleadingly named
                # 'stage2_converged' in the first v2 cut)
                "welfare_equalized": cf.get("welfare_equalized",
                                            cf.get("stage2_converged", "")),
                # Solver convergence (per stage; separate from welfare equalization)
                "s1_iter_converged": cf.get("s1_iter_converged", ""),
                "s1_iter_diff": cf.get("s1_iter_diff", ""),
                "s2_iter_converged": cf.get("s2_iter_converged", ""),
                "s2_iter_diff": cf.get("s2_iter_diff", ""),
                "s3_iter_converged": cf.get("s3_iter_converged", ""),
                "s3_iter_diff": cf.get("s3_iter_diff", ""),
                # Stage 3 (finite-κ frictional mobility)
                "welfare_s3_pct": cf.get("welfare_s3_pct", ""),
                "welfare_s3_cv": cf.get("welfare_s3_cv", ""),
                "kappa": cf.get("kappa", ""),
                # Calibration metadata
                "calibration_version": cf.get("calibration_version",
                                              params.get("calibration_version", "")),
                "scale_calibration_status": params.get("scale_calibration_status", ""),
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
        print(f"\n{'Country':<25s} {'Region':<18s} {'S1':>8s} {'S2':>8s} {'S3':>8s} {'S3 CV':>8s} {'Distr':>8s}")
        print(f"{'-'*85}")
        for _, row in success.sort_values("welfare_pct", ascending=False).iterrows():
            def fmt_pct(v):
                return f"{v:+.1f}%" if isinstance(v, (int, float)) else str(v)
            def fmt_cv(v):
                return f"{v:.3f}" if isinstance(v, (int, float)) else str(v)
            print(f"{row['country_name']:<25s} {row['region']:<18s} "
                  f"{fmt_pct(row.get('welfare_s1_pct','')):>8s} "
                  f"{fmt_pct(row.get('welfare_pct','')):>8s} "
                  f"{fmt_pct(row.get('welfare_s3_pct','')):>8s} "
                  f"{fmt_cv(row.get('welfare_s3_cv','')):>8s} "
                  f"{row.get('n_districts',''):>8}")

        # Convergence flag summary
        cvs = success["welfare_cv"]
        cvs_num = pd.to_numeric(cvs, errors="coerce")
        non_conv = cvs_num[cvs_num > 0.05]
        if len(non_conv) > 0:
            print(f"\n  WARNING: {len(non_conv)} countries with welfare_cv > 0.05 (Stage 2 not equalized):")
            for idx, cv in non_conv.items():
                country_name = success.loc[idx, "country_name"]
                print(f"    {country_name}: cv={cv:.3f}")

    missing = df[df["status"] != "success"]
    if len(missing) > 0:
        print(f"\nMissing/failed ({len(missing)}):")
        for _, row in missing.iterrows():
            print(f"  {row['iso3']} {row['country_name']}: {row['status']}")

    print(f"\nSaved to {out_path}")
    return df


def collect_data_summary():
    """Collect road data and model summaries for all countries."""
    registry = load_registry()
    rows = []

    for _, country in registry.iterrows():
        cfg = build_config(country)
        name_lower = country["country_name"].lower().replace(" ", "_").replace("'", "")

        row = {
            "country_name": country["country_name"],
            "iso3": country["iso3"],
            "region": country["region"],
            "national_gdp_2019": country["national_gdp_2019"],
        }

        # Road summary (from Phase 1)
        road_path = f"data/processed/{name_lower}_road_summary.json"
        if os.path.exists(road_path):
            with open(road_path) as f:
                roads = json.load(f)
            row.update({
                "total_road_km": roads.get("total_km", ""),
                "total_segments": roads.get("total_segments", ""),
                "paved_km": roads.get("paved_km", ""),
                "paved_pct": roads.get("paved_pct", ""),
                "unpaved_km": roads.get("unpaved_km", ""),
                "unpaved_pct": roads.get("unpaved_pct", ""),
                "unknown_km": roads.get("unknown_km", ""),
                "unknown_pct": roads.get("unknown_pct", ""),
                "osm_coverage_pct": roads.get("osm_coverage_pct", ""),
            })

        # Model params (from Phase 3)
        params_path = cfg["model_params"]
        if os.path.exists(params_path):
            with open(params_path) as f:
                params = json.load(f)
            row.update({
                "n_districts": params.get("n_districts", ""),
                "total_population": params.get("total_population", ""),
                "trade_cost_scale": params.get("trade_cost_scale", ""),
                "median_pi_nn": params.get("median_pi_nn", ""),
            })

        rows.append(row)

    if rows:
        df = pd.DataFrame(rows)
        out_path = os.path.join(OUTPUT_DIR, "ssa_data_summary.csv")
        df.to_csv(out_path, index=False)
        print(f"\nData summary: {len(df)} countries → {out_path}")

        # Print road coverage ranking
        has_roads = df[df.get("osm_coverage_pct", pd.Series(dtype=str)).notna() & (df.get("osm_coverage_pct", pd.Series(dtype=str)) != "")].copy() if "osm_coverage_pct" in df.columns else pd.DataFrame()
        if len(has_roads) > 0:
            has_roads["osm_coverage_pct"] = has_roads["osm_coverage_pct"].astype(float)
            has_roads = has_roads.sort_values("osm_coverage_pct", ascending=False)
            print(f"\nOSM Surface Coverage Ranking:")
            for _, r in has_roads.iterrows():
                print(f"  {r['iso3']} {r['country_name']:<25s} {r['osm_coverage_pct']:>5.1f}%  "
                      f"({r.get('paved_pct', '?'):.1f}% paved)")

        return df
    return None


def main():
    collect_model_results()
    collect_data_summary()


if __name__ == "__main__":
    main()
