"""
sensitivity_unknown.py — Full sensitivity to unknown road classification.

Rebuilds the road graph, trade costs, calibration, and counterfactual
from scratch for each cost_unknown assumption. This is the proper test —
shortest paths may change when edge weights change.

Usage:
    python3 src/sensitivity_unknown.py --iso3 TZA
    python3 src/sensitivity_unknown.py --iso3 KEN

Tests three scenarios:
  1. unknown = 1.0 (treat all unknown as paved — optimistic)
  2. unknown = 2.0 (midpoint — current baseline)
  3. unknown = 3.0 (treat all unknown as unpaved — pessimistic)

Note (v2): under the new calibration, each scenario gets its own scale
calibrated to hit median π_nn = 0.4 (R&RH benchmark). That common
trade-share moment makes scenarios genuinely comparable — what differs
is the network structure under each scenario, not the iceberg level.
"""

import os
import sys
import time
import json
import argparse
import numpy as np
import geopandas as gpd

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from country_config import get_config_by_iso3

# Import phase functions from run_country
from run_country import (
    phase1_extract_roads, phase2_trade_costs,
    phase3_calibrate, phase4_counterfactual
)


def run_scenario(cfg, cost_unknown, label):
    """Run full Phases 2-4 with a specific cost_unknown value."""
    print(f"\n{'#'*60}")
    print(f"  SCENARIO: {label} (cost_unknown = {cost_unknown})")
    print(f"{'#'*60}")

    # Override cost_unknown
    cfg_mod = cfg.copy()
    cfg_mod["cost_unknown"] = cost_unknown

    # Modify output paths to avoid overwriting main results
    suffix = f"_unk{cost_unknown:.0f}"
    name_lower = cfg["country_name"].lower().replace(" ", "_").replace("'", "")
    cfg_mod["admin_gpkg"] = f"data/processed/{name_lower}_admin2{suffix}.gpkg"
    cfg_mod["trade_costs_baseline"] = f"data/processed/{name_lower}_trade_costs_baseline{suffix}.npy"
    cfg_mod["trade_costs_counterfactual"] = f"data/processed/{name_lower}_trade_costs_counterfactual{suffix}.npy"
    cfg_mod["admin_names"] = f"data/processed/{name_lower}_admin2_names{suffix}.npy"
    cfg_mod["calibrated_gpkg"] = f"data/processed/{name_lower}_calibrated{suffix}.gpkg"
    cfg_mod["trade_shares"] = f"data/processed/{name_lower}_baseline_trade_shares{suffix}.npy"
    cfg_mod["model_params"] = f"data/processed/{name_lower}_model_params{suffix}.json"
    cfg_mod["counterfactual_gpkg"] = f"data/processed/{name_lower}_counterfactual{suffix}.gpkg"
    cfg_mod["counterfactual_results"] = f"data/processed/{name_lower}_counterfactual_results{suffix}.json"

    t0 = time.time()

    # Phase 2: rebuild graph with new cost_unknown
    admin, tc_base, tc_cf = phase2_trade_costs(cfg_mod)

    # Phase 3: recalibrate
    admin_cal, pop, gdp, pi, A = phase3_calibrate(cfg_mod, admin, tc_base)

    # Phase 4: counterfactual
    welfare = phase4_counterfactual(cfg_mod, admin_cal, pop, gdp, pi, tc_base, tc_cf)

    elapsed = time.time() - t0

    # Read some stats
    with open(cfg_mod["model_params"]) as f:
        params = json.load(f)

    return {
        "label": label,
        "cost_unknown": cost_unknown,
        "welfare_pct": welfare,
        "median_pi_nn": params.get("median_pi_nn", None),
        "runtime_min": elapsed / 60,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iso3", required=True, help="Country ISO3 code")
    args = parser.parse_args()

    cfg = get_config_by_iso3(args.iso3)
    country = cfg["country_name"]

    print(f"\n{'='*60}")
    print(f"UNKNOWN ROAD SENSITIVITY: {country}")
    print(f"{'='*60}")
    print(f"Testing: what if unknown-surface roads are paved vs unpaved?")

    # Phase 1 only needs to run once (road extraction doesn't depend on cost_unknown)
    roads_path = cfg["roads_gpkg"]
    if not os.path.exists(roads_path):
        print("\nRunning Phase 1 (road extraction)...")
        phase1_extract_roads(cfg)
    else:
        print(f"\nPhase 1 already done: {roads_path}")

    scenarios = [
        (1.0, "Unknown = PAVED (optimistic)"),
        (2.0, "Unknown = MIDPOINT (baseline)"),
        (3.0, "Unknown = UNPAVED (pessimistic)"),
    ]

    results = []
    for cost_unk, label in scenarios:
        r = run_scenario(cfg, cost_unk, label)
        results.append(r)

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY: {country}")
    print(f"{'='*60}")
    print(f"\n{'Scenario':<40s} {'Welfare':>10s} {'pi_nn':>10s} {'Time':>8s}")
    print(f"{'-'*70}")
    for r in results:
        pi_str = f"{r['median_pi_nn']:.3f}" if r['median_pi_nn'] else "N/A"
        print(f"{r['label']:<40s} {r['welfare_pct']:>+10.1f}% {pi_str:>10s} {r['runtime_min']:>7.1f}m")

    spread = max(r["welfare_pct"] for r in results) - min(r["welfare_pct"] for r in results)
    print(f"\nSpread: {spread:.1f} percentage points")
    if spread < 10:
        print("Result is ROBUST to unknown road classification.")
    else:
        print("Result is SENSITIVE to unknown road classification — need better surface data.")

    # Save
    out_path = f"outputs/welfare_sensitivity_unknown_{args.iso3}.txt"
    os.makedirs("outputs", exist_ok=True)
    with open(out_path, "w") as f:
        f.write(f"Unknown Road Classification Sensitivity: {country}\n")
        f.write("=" * 50 + "\n\n")
        for r in results:
            f.write(f"{r['label']}: welfare = {r['welfare_pct']:+.1f}%\n")
        f.write(f"\nSpread: {spread:.1f} pp\n")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
