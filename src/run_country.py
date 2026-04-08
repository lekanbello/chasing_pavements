"""
run_country.py — Run the full Phases 1-4 pipeline for a single country.

Usage:
    python3 src/run_country.py configs/kenya.yaml
    python3 src/run_country.py configs/tanzania.yaml

Reads a YAML config file and runs:
  Phase 1: Extract and classify roads from OSM PBF
  Phase 2: Build road network graph, compute trade cost matrices
  Phase 3: Aggregate population/GDP, calibrate GE model
  Phase 4: Solve counterfactual (pave all roads), compute welfare
"""

import os
import sys
import time
import json
import yaml
import numpy as np
import geopandas as gpd
import pandas as pd
import osmium
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import shortest_path, connected_components
from rasterstats import zonal_stats
from shapely.geometry import LineString, Point, box


# ══════════════════════════════════════════════════════════════════════
# PHASE 1: Road Extraction
# ══════════════════════════════════════════════════════════════════════

ROAD_CLASSES = {
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link", "unclassified", "residential", "track",
}
PAVED = {"paved", "asphalt", "concrete", "concrete:plates", "concrete:lanes",
         "sett", "cobblestone", "metal", "wood", "bricks"}
UNPAVED = {"unpaved", "gravel", "fine_gravel", "compacted", "dirt", "earth",
           "grass", "ground", "mud", "sand", "soil", "rock"}


def classify_surface(tag):
    if tag is None or tag == "":
        return "unknown"
    t = tag.strip().lower()
    if t in PAVED: return "paved"
    if t in UNPAVED: return "unpaved"
    return "unknown"


class RoadHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.roads = []

    def way(self, w):
        hw = w.tags.get("highway")
        if hw not in ROAD_CLASSES:
            return
        try:
            coords = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(coords) < 2:
            return
        self.roads.append({
            "osm_id": w.id, "highway": hw,
            "surface": w.tags.get("surface"),
            "geometry": LineString(coords),
        })


def phase1_extract_roads(cfg):
    """Extract roads from OSM PBF, classify surfaces, save."""
    pbf = cfg["osm_pbf"]
    out = cfg["roads_gpkg"]
    utm = cfg["utm_epsg"]

    print(f"\n{'='*60}")
    print(f"PHASE 1: Extracting roads from {os.path.basename(pbf)}")
    print(f"{'='*60}")

    handler = RoadHandler()
    handler.apply_file(pbf, locations=True)
    print(f"  Extracted {len(handler.roads):,} road segments")

    gdf = gpd.GeoDataFrame(handler.roads, crs="EPSG:4326")
    gdf["surface_class"] = gdf["surface"].apply(classify_surface)
    gdf["length_km"] = gdf.to_crs(f"EPSG:{utm}").geometry.length / 1000.0

    total_km = gdf["length_km"].sum()
    for sc in ["paved", "unpaved", "unknown"]:
        km = gdf.loc[gdf["surface_class"] == sc, "length_km"].sum()
        print(f"  {sc:10s}: {km:>10,.0f} km ({100*km/total_km:.1f}%)")
    print(f"  {'TOTAL':10s}: {total_km:>10,.0f} km")

    os.makedirs(os.path.dirname(out), exist_ok=True)
    gdf.to_file(out, driver="GPKG")
    print(f"  Saved: {out}")
    return gdf


# ══════════════════════════════════════════════════════════════════════
# PHASE 2: Trade Costs
# ══════════════════════════════════════════════════════════════════════

class GraphHandler(osmium.SimpleHandler):
    def __init__(self, cost_paved, cost_unpaved, cost_unknown):
        super().__init__()
        self.edges = []
        self.node_locs = {}
        self.cp = cost_paved
        self.cu = cost_unpaved
        self.ck = cost_unknown

    def way(self, w):
        hw = w.tags.get("highway")
        if hw not in ROAD_CLASSES:
            return
        sc = classify_surface(w.tags.get("surface"))
        mult = self.cp if sc == "paved" else (self.cu if sc == "unpaved" else self.ck)
        try:
            nodes = [(n.ref, n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(nodes) < 2:
            return
        for ref, lon, lat in nodes:
            self.node_locs[ref] = (lon, lat)
        for k in range(1, len(nodes)):
            r0, lo0, la0 = nodes[k-1]
            r1, lo1, la1 = nodes[k]
            dlat, dlon = la1-la0, lo1-lo0
            mid = (la1+la0)/2
            dx = dlon * 111.32 * np.cos(np.radians(mid))
            dy = dlat * 111.32
            dist = np.sqrt(dx*dx + dy*dy)
            if dist > 0 and r0 != r1:
                self.edges.append((r0, r1, dist * mult, sc))


def phase2_trade_costs(cfg):
    """Build graph, compute shortest paths, save trade cost matrices."""
    pbf = cfg["osm_pbf"]
    gadm = cfg["gadm_gpkg"]
    gadm_layer = cfg["gadm_layer"]
    utm = cfg["utm_epsg"]
    cp = cfg["cost_paved"]
    cu = cfg["cost_unpaved"]
    ck = cfg["cost_unknown"]

    print(f"\n{'='*60}")
    print(f"PHASE 2: Computing trade costs")
    print(f"{'='*60}")

    # Load admin boundaries
    admin = gpd.read_file(gadm, layer=gadm_layer)
    admin_proj = admin.to_crs(f"EPSG:{utm}")
    centroids_proj = admin_proj.geometry.centroid
    centroids_wgs = centroids_proj.to_crs("EPSG:4326")
    admin["centroid_lon"] = centroids_wgs.x
    admin["centroid_lat"] = centroids_wgs.y
    n_admin = len(admin)
    print(f"  {n_admin} admin-2 districts")

    def build_graph(cost_p, cost_u, cost_k):
        handler = GraphHandler(cost_p, cost_u, cost_k)
        handler.apply_file(pbf, locations=True)
        osm_to_id = {}
        nxt = 0
        for ref in handler.node_locs:
            osm_to_id[ref] = nxt
            nxt += 1
        n_nodes = nxt
        node_coords = {osm_to_id[r]: loc for r, loc in handler.node_locs.items()}

        from collections import defaultdict
        edge_min = defaultdict(lambda: float('inf'))
        for s, e, cost, _ in handler.edges:
            u, v = osm_to_id[s], osm_to_id[e]
            key = (min(u,v), max(u,v))
            if cost < edge_min[key]:
                edge_min[key] = cost

        rows, cols, weights = [], [], []
        for (u,v), w in edge_min.items():
            rows.extend([u,v]); cols.extend([v,u]); weights.extend([w,w])

        adj = coo_matrix((np.array(weights), (np.array(rows), np.array(cols))),
                         shape=(n_nodes, n_nodes)).tocsr()

        # Simplify: identify intersections
        degree = np.array(adj.getnnz(axis=1)).ravel()
        is_intersection = degree != 2
        # For simplicity, keep full graph — simplification can be added later

        nc, labels = connected_components(adj, directed=False)
        sizes = np.bincount(labels)
        largest = sizes.max()
        print(f"    Nodes: {n_nodes:,}, Edges: {len(edge_min):,}, "
              f"Components: {nc:,}, Largest: {largest:,} ({100*largest/n_nodes:.1f}%)")

        return node_coords, adj

    print("  Building baseline graph...")
    node_coords, adj_base = build_graph(cp, cu, ck)

    print("  Building counterfactual graph (all paved)...")
    _, adj_cf = build_graph(cp, cp, cp)

    # Snap centroids
    node_ids = np.array(list(node_coords.keys()))
    node_lons = np.array([node_coords[nid][0] for nid in node_ids])
    node_lats = np.array([node_coords[nid][1] for nid in node_ids])

    snap_nodes = []
    for i in range(n_admin):
        dists = np.sqrt((node_lons - admin.iloc[i]["centroid_lon"])**2 +
                        (node_lats - admin.iloc[i]["centroid_lat"])**2)
        snap_nodes.append(int(node_ids[np.argmin(dists)]))

    # Shortest paths
    print("  Computing baseline shortest paths...")
    tc_base = np.full((n_admin, n_admin), np.inf)
    for i in range(n_admin):
        d = shortest_path(adj_base, method='D', directed=False, indices=snap_nodes[i])
        for j in range(n_admin):
            tc_base[i, j] = d[snap_nodes[j]]

    print("  Computing counterfactual shortest paths...")
    tc_cf = np.full((n_admin, n_admin), np.inf)
    for i in range(n_admin):
        d = shortest_path(adj_cf, method='D', directed=False, indices=snap_nodes[i])
        for j in range(n_admin):
            tc_cf[i, j] = d[snap_nodes[j]]

    # Stats
    mask = np.isfinite(tc_base) & (tc_base > 0) & ~np.eye(n_admin, dtype=bool)
    connected_pct = 100 * mask.sum() / (n_admin * (n_admin - 1))
    both = mask & np.isfinite(tc_cf) & (tc_cf > 0)
    if both.any():
        reductions = 100 * (1 - tc_cf[both] / tc_base[both])
        print(f"  Connected pairs: {connected_pct:.1f}%")
        print(f"  Mean trade cost reduction: {reductions.mean():.1f}%")

    # Save
    admin["snap_node_id"] = snap_nodes
    admin.to_file(cfg["admin_gpkg"], driver="GPKG")
    np.save(cfg["trade_costs_baseline"], tc_base)
    np.save(cfg["trade_costs_counterfactual"], tc_cf)
    names = [f"{admin.iloc[i]['NAME_2']} ({admin.iloc[i]['NAME_1']})" for i in range(n_admin)]
    np.save(cfg["admin_names"], names)
    print(f"  Saved trade cost matrices and admin data")

    return admin, tc_base, tc_cf


# ══════════════════════════════════════════════════════════════════════
# PHASE 3: Calibration
# ══════════════════════════════════════════════════════════════════════

def phase3_calibrate(cfg, admin, tc_base):
    """Aggregate population/GDP, invert GE model."""
    print(f"\n{'='*60}")
    print(f"PHASE 3: Model calibration")
    print(f"{'='*60}")

    n = len(admin)
    utm = cfg["utm_epsg"]

    # Population
    wp_path = cfg["worldpop_path"]
    if not os.path.exists(wp_path):
        print(f"  Downloading WorldPop...")
        import requests
        r = requests.get(cfg["worldpop_url"], stream=True)
        with open(wp_path, 'wb') as f:
            for chunk in r.iter_content(131072):
                f.write(chunk)
        print(f"  Downloaded: {os.path.getsize(wp_path)/1e6:.0f} MB")

    print("  Aggregating population...")
    stats = zonal_stats(admin.geometry, wp_path, stats=["sum"], nodata=-99999)
    population = np.array([s["sum"] if s["sum"] is not None else 0.0 for s in stats])
    print(f"  Total population: {population.sum():,.0f}")

    # GDP
    national_gdp = cfg["national_gdp_fallback"]
    try:
        import wbgapi as wb
        df = wb.data.DataFrame("NY.GDP.MKTP.CD", cfg["iso3"], time=cfg["year"])
        national_gdp = df.iloc[0, 0]
        print(f"  GDP from WDI: ${national_gdp:,.0f}")
    except:
        print(f"  GDP (cached): ${national_gdp:,.0f}")

    # BFI GDP allocation (population-weighted overlay)
    bfi_dir = "data/raw/bfi_gdp_025deg"
    csv_path = os.path.join(bfi_dir, "0_25deg_v2",
                            "final_GDPC_0_25deg_postadjust_pop_dens_no_extra_adjust.csv")
    if os.path.exists(csv_path):
        print("  Aggregating BFI GDP...")
        df = pd.read_csv(csv_path)
        tz = df[(df["iso"] == cfg["iso3"]) & (df["year"] == cfg["year"])].copy()
        if len(tz) > 0:
            half = 0.125
            polys = [box(r["longitude"]-half, r["latitude"]-half,
                        r["longitude"]+half, r["latitude"]+half) for _, r in tz.iterrows()]
            bfi = gpd.GeoDataFrame(tz, geometry=polys, crs="EPSG:4326")
            sindex = admin.sindex
            district_gdp = np.zeros(n)
            for _, cell in bfi.iterrows():
                if cell["predicted_GCP_current_USD"] <= 0:
                    continue
                possible = list(sindex.intersection(cell.geometry.bounds))
                overlapping = {j: population[j] for j in possible
                              if cell.geometry.intersects(admin.iloc[j].geometry)}
                total_pop = sum(overlapping.values())
                if total_pop > 0:
                    for j, pop in overlapping.items():
                        district_gdp[j] += cell["predicted_GCP_current_USD"] * (pop / total_pop)
            total_share = district_gdp.sum()
            if total_share > 0:
                gdp = (district_gdp / total_share) * national_gdp
            else:
                gdp = (population / population.sum()) * national_gdp
        else:
            print(f"  No BFI data for {cfg['iso3']}, using population weights")
            gdp = (population / population.sum()) * national_gdp
    else:
        gdp = (population / population.sum()) * national_gdp

    # Floor
    pop_floor = np.median(population[population > 0]) * 0.01
    gdp_floor = np.median(gdp[gdp > 0]) * 0.01
    population = np.maximum(population, pop_floor)
    gdp = np.maximum(gdp, gdp_floor)

    # Trade cost normalization
    tc = tc_base.copy()
    finite = np.isfinite(tc) & (tc > 0)
    max_f = tc[finite].max()
    tc[~np.isfinite(tc)] = max_f * 2
    np.fill_diagonal(tc, 0)
    off = tc[~np.eye(n, dtype=bool) & (tc > 0)]
    scale = np.median(off) / 4.0
    tau = 1.0 + tc / scale
    np.fill_diagonal(tau, 1.0)
    print(f"  Trade cost scale: {scale:.0f} km, median τ: {np.median(tau[tau>1]):.2f}")

    # Inversion
    theta = cfg["parameters"]["theta"]
    alpha = cfg["parameters"]["alpha"]
    kappa = cfg["parameters"]["kappa"]
    w = gdp / population
    A = (gdp / population) / np.median(gdp / population)
    A = np.maximum(A, 1e-10)

    print("  Inverting model...")
    for iteration in range(3000):
        A_old = A.copy()
        cost = np.outer(w**alpha, np.ones(n)) * tau
        num = np.outer(A**theta, np.ones(n)) * cost**(-theta)
        Phi = num.sum(axis=0)
        Phi = np.maximum(Phi, 1e-300)
        pi = num / Phi[np.newaxis, :]
        Y_pred = pi @ gdp
        ratio = gdp / np.maximum(Y_pred, 1e-10)
        A = A * ratio**(0.3 / theta)
        A = np.maximum(A, 1e-10)
        diff = np.max(np.abs(np.log(A) - np.log(A_old)))
        if diff < 1e-4:
            print(f"  Converged at iteration {iteration}")
            break

    pi_nn = np.diag(pi)
    P = Phi**(-1.0 / theta)
    a = (population / population.sum())**(1.0 / kappa) * P / w
    a = a / a.mean()

    print(f"  Median pi_nn: {np.median(pi_nn):.3f}")
    print(f"  Productivity range: {A.min():.3f} - {A.max():.3f}")

    # Save
    admin_out = admin.copy()
    admin_out["population"] = population
    admin_out["gdp_usd"] = gdp
    admin_out["productivity"] = A
    admin_out["amenity"] = a
    admin_out["price_index"] = P
    admin_out.to_file(cfg["calibrated_gpkg"], driver="GPKG")
    np.save(cfg["trade_shares"], pi)
    json.dump({
        "year": cfg["year"], "national_gdp_usd": float(national_gdp),
        "total_population": float(population.sum()), "n_districts": n,
        "parameters": cfg["parameters"], "trade_cost_scale": float(scale),
        "median_pi_nn": float(np.median(pi_nn)),
    }, open(cfg["model_params"], "w"), indent=2)
    print(f"  Saved calibrated model")

    return admin_out, population, gdp, pi, A


# ══════════════════════════════════════════════════════════════════════
# PHASE 4: Counterfactual
# ══════════════════════════════════════════════════════════════════════

def phase4_counterfactual(cfg, admin, population, gdp, pi_full, tc_base, tc_cf):
    """Solve counterfactual and compute welfare."""
    print(f"\n{'='*60}")
    print(f"PHASE 4: Counterfactual (pave all roads)")
    print(f"{'='*60}")

    sigma = cfg["parameters"]["sigma"]
    alpha = cfg["parameters"]["alpha"]
    n = len(admin)

    # Filter districts
    L, Y = population, gdp
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        name = admin.iloc[i]["NAME_2"]
        if any(w in str(name).lower() for w in ["lake ", "mafia"]):
            keep[i] = False
        if L[i] < 1000:
            keep[i] = False
        row = tc_base[i, :]
        if not (np.isfinite(row) & (np.arange(n) != i) & (row > 0)).any():
            keep[i] = False

    idx = np.where(keep)[0]
    nn = len(idx)
    print(f"  Keeping {nn} / {n} districts")

    L_s = L[idx]; Y_s = Y[idx]
    tc_b = tc_base[np.ix_(idx, idx)]; tc_c = tc_cf[np.ix_(idx, idx)]
    pi = pi_full[np.ix_(idx, idx)]
    pi = pi / pi.sum(axis=1, keepdims=True)

    # d_hat
    conn = np.isfinite(tc_b) & np.isfinite(tc_c) & (tc_b > 0) & (tc_c > 0)
    np.fill_diagonal(conn, True)
    d_hat = np.ones((nn, nn))
    mask = conn & ~np.eye(nn, dtype=bool)
    d_hat[mask] = tc_c[mask] / tc_b[mask]

    reduced = d_hat[mask & (d_hat < 0.999)]
    print(f"  Mean d_hat reduction: {100*(1-reduced.mean()):.1f}%")

    w = Y_s / L_s
    lam = L_s / L_s.sum()
    wl = w * lam
    pi_nn = np.diag(pi)

    # Stage 1: fixed population
    print("  Stage 1 (fixed pop)...")
    w_hat = np.ones(nn)
    for it in range(5000):
        w_hat_old = w_hat.copy()
        factor = (d_hat * w_hat[np.newaxis, :])**(1 - sigma)
        num = pi * factor
        pi_p = num / num.sum(axis=1, keepdims=True)
        rhs = pi_p.T @ (w_hat * wl)
        w_hat_new = rhs / wl
        w_hat = w_hat**0.7 * np.maximum(w_hat_new, 1e-20)**0.3
        w_hat = w_hat / np.average(w_hat, weights=wl)
        if np.max(np.abs(np.log(w_hat) - np.log(w_hat_old))) < 1e-6:
            break

    pi_nn_p1 = np.diag(pi_p)
    exp1 = alpha / (sigma - 1)
    welfare_s1 = np.average(w_hat * (pi_nn / np.maximum(pi_nn_p1, 1e-20))**exp1, weights=L_s)
    print(f"  Stage 1 welfare: {100*(welfare_s1-1):+.1f}%")

    # Stage 2: with mobility
    print("  Stage 2 (with mobility)...")
    lam_hat = np.ones(nn)
    gamma = alpha / (sigma * (1 - alpha) - 1)

    for it in range(5000):
        w_hat_old = w_hat.copy()
        lam_hat_old = lam_hat.copy()
        L_hat = lam_hat

        factor = (d_hat * w_hat[np.newaxis, :])**(1-sigma) * L_hat[np.newaxis, :]
        num = pi * factor
        pi_p = num / num.sum(axis=1, keepdims=True)
        pi_nn_p = np.diag(pi_p)
        pi_nn_hat = pi_nn_p / np.maximum(pi_nn, 1e-300)

        pi_exp = np.clip(pi_nn_hat, 1e-10, 1e10)**(-gamma)
        lam_hat_new = pi_exp / np.sum(pi_exp * lam)

        rhs = pi_p.T @ (w_hat * lam_hat * wl)
        w_hat_new = rhs / np.maximum(lam_hat * wl, 1e-300)

        w_hat = w_hat**0.9 * np.clip(w_hat_new, 0.1, 10)**0.1
        lam_hat = lam_hat**0.9 * np.clip(lam_hat_new, 0.1, 10)**0.1
        w_hat = w_hat / np.average(w_hat, weights=wl)

        diff = max(np.max(np.abs(np.log(w_hat) - np.log(w_hat_old))),
                   np.max(np.abs(np.log(np.maximum(lam_hat, 1e-20)) -
                                  np.log(np.maximum(lam_hat_old, 1e-20)))))
        if diff < 1e-7:
            break

    # Welfare (Eq 21)
    exp2 = (sigma * (1-alpha) - 1) / (sigma - 1)
    lam_p = lam_hat * lam
    pi_nn_final = np.diag(pi_p)
    welfare_loc = (pi_nn / np.maximum(pi_nn_final, 1e-20))**exp1 * (lam / np.maximum(lam_p, 1e-20))**exp2
    welfare = np.median(welfare_loc)
    welfare_pct = 100 * (welfare - 1)

    print(f"\n  ┌─────────────────────────────────────────┐")
    print(f"  │  {cfg['country_name']:>10s} Welfare Gain: {welfare_pct:>+6.1f}%     │")
    print(f"  │  Stage 1 (fixed pop):    {100*(welfare_s1-1):>+6.1f}%     │")
    print(f"  └─────────────────────────────────────────┘")

    # Save
    admin_sub = admin.iloc[idx].reset_index(drop=True)
    admin_sub["welfare_pct"] = 100 * (welfare_loc - 1)
    admin_sub["pop_hat"] = lam_hat
    admin_sub.to_file(cfg["counterfactual_gpkg"], driver="GPKG")

    json.dump({
        "country": cfg["country_name"], "year": cfg["year"],
        "parameters": cfg["parameters"],
        "n_districts": nn, "n_total": n,
        "welfare_pct": float(welfare_pct),
        "welfare_s1_pct": float(100*(welfare_s1-1)),
    }, open(cfg["counterfactual_results"], "w"), indent=2)

    return welfare_pct


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run Chasing Pavements pipeline")
    parser.add_argument("config", help="Path to country YAML config")
    parser.add_argument("--phase", type=int, default=0,
                        help="Run specific phase (1-4). Default 0 = all phases.")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    phase = args.phase
    country = cfg["country_name"]

    print(f"\n{'#'*60}")
    print(f"  CHASING PAVEMENTS: {country.upper()}")
    if phase:
        print(f"  Running Phase {phase} only")
    print(f"{'#'*60}")

    t0 = time.time()

    if phase == 0 or phase == 1:
        roads = phase1_extract_roads(cfg)

    if phase == 0 or phase == 2:
        admin, tc_base, tc_cf = phase2_trade_costs(cfg)

    if phase == 0 or phase == 3:
        # Load admin and trade costs if not already in memory
        if phase == 3:
            admin = gpd.read_file(cfg["admin_gpkg"])
            tc_base = np.load(cfg["trade_costs_baseline"])
        admin_cal, pop, gdp, pi, A = phase3_calibrate(cfg, admin, tc_base)

    if phase == 0 or phase == 4:
        # Load everything if not in memory
        if phase == 4:
            admin_cal = gpd.read_file(cfg["calibrated_gpkg"])
            pop = admin_cal["population"].values
            gdp = admin_cal["gdp_usd"].values
            pi = np.load(cfg["trade_shares"])
            tc_base = np.load(cfg["trade_costs_baseline"])
            tc_cf = np.load(cfg["trade_costs_counterfactual"])
        welfare = phase4_counterfactual(cfg, admin_cal, pop, gdp, pi, tc_base, tc_cf)

    elapsed = time.time() - t0
    print(f"\n  Completed in {elapsed/60:.1f} minutes")
    print(f"{'#'*60}")


if __name__ == "__main__":
    main()
