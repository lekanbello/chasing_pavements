"""
network.py — Build road network graph and compute bilateral trade costs.

Takes the processed road GeoDataFrame from ingest.py, constructs a weighted
graph, snaps admin-2 centroids to the network, and computes shortest-path
trade cost matrices (baseline and counterfactual).
"""

import os
import sys
import time
import numpy as np
import geopandas as gpd
import osmium
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import shortest_path, connected_components
from shapely.geometry import Point

# ── Configuration ──────────────────────────────────────────────────────

PBF_PATH = "data/raw/tanzania-latest.osm.pbf"
ROADS_PATH = "data/processed/tanzania_roads.gpkg"
GADM_PATH = "data/raw/gadm41_TZA.gpkg"
GADM_LAYER = "ADM_ADM_2"

OUTPUT_DIR = "data/processed"
ADMIN_OUTPUT = os.path.join(OUTPUT_DIR, "tanzania_admin2.gpkg")
BASELINE_OUTPUT = os.path.join(OUTPUT_DIR, "tanzania_trade_costs_baseline.npy")
COUNTERFACTUAL_OUTPUT = os.path.join(OUTPUT_DIR, "tanzania_trade_costs_counterfactual.npy")
NODE_NAMES_OUTPUT = os.path.join(OUTPUT_DIR, "tanzania_admin2_names.npy")

# Cost multipliers (placeholder — to be replaced with Google Maps estimates)
COST_PAVED = 1.0
COST_UNPAVED = 3.0
COST_UNKNOWN = 2.0  # midpoint assumption


# ── Graph Construction ─────────────────────────────────────────────────

# ── OSM Road classes (same as ingest.py) ───────────────────────────────

ROAD_CLASSES = {
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "unclassified",
    "residential",
    "track",
}

PAVED_SURFACES = {
    "paved", "asphalt", "concrete", "concrete:plates", "concrete:lanes",
    "sett", "cobblestone", "metal", "wood", "bricks",
}
UNPAVED_SURFACES = {
    "unpaved", "gravel", "fine_gravel", "compacted", "dirt", "earth",
    "grass", "ground", "mud", "sand", "soil", "rock",
}


def _classify_surface(tag):
    if tag is None or tag == "":
        return "unknown"
    tag = tag.strip().lower()
    if tag in PAVED_SURFACES:
        return "paved"
    elif tag in UNPAVED_SURFACES:
        return "unpaved"
    return "unknown"


class WayCollector(osmium.SimpleHandler):
    """
    First pass: collect road ways as lists of (node_ref, surface_class).
    Also count how many ways each node appears in to identify intersections.
    """

    def __init__(self):
        super().__init__()
        self.ways = []  # [(node_refs, surface_class), ...]
        self.node_way_count = {}  # osm_node_ref -> count of ways using it

    def way(self, w):
        highway = w.tags.get("highway")
        if highway not in ROAD_CLASSES:
            return

        surface_class = _classify_surface(w.tags.get("surface"))

        try:
            refs = [n.ref for n in w.nodes]
            locs = {n.ref: (n.lon, n.lat) for n in w.nodes}
        except osmium.InvalidLocationError:
            return

        if len(refs) < 2:
            return

        self.ways.append((refs, locs, surface_class))

        # Count node appearances across ways
        for ref in refs:
            self.node_way_count[ref] = self.node_way_count.get(ref, 0) + 1


def parse_simplified_graph(pbf_path):
    """
    Parse PBF and build a simplified graph with only intersection nodes.

    An intersection is a node that appears in 2+ ways, or is an endpoint of a way.
    Intermediate nodes are contracted — distances are summed along the chain.

    This reduces the graph from ~28M nodes to ~200K-500K.

    Returns:
        edges: list of (compact_u, compact_v, dist_km, surface_class)
        node_coords: dict mapping compact_id -> (lon, lat)
        n_nodes: int
    """
    print(f"  Parsing {pbf_path}...")
    t0 = time.time()

    handler = WayCollector()
    handler.apply_file(pbf_path, locations=True)

    n_ways = len(handler.ways)
    n_raw_nodes = len(handler.node_way_count)
    print(f"  {n_ways:,} road ways, {n_raw_nodes:,} raw nodes")

    # Identify intersection nodes: appear in 2+ ways or are way endpoints
    intersection_nodes = set()
    for refs, locs, sc in handler.ways:
        intersection_nodes.add(refs[0])   # start of way
        intersection_nodes.add(refs[-1])  # end of way
    for ref, count in handler.node_way_count.items():
        if count >= 2:
            intersection_nodes.add(ref)

    print(f"  Intersection/endpoint nodes: {len(intersection_nodes):,}")

    # Compact IDs for intersection nodes only
    all_node_locs = {}
    osm_to_compact = {}
    next_id = 0

    # Build simplified edges: walk each way, accumulate distance between intersections
    edges = []

    for refs, locs, surface_class in handler.ways:
        # Store locations for intersection nodes
        for ref in refs:
            if ref in intersection_nodes and ref not in osm_to_compact:
                osm_to_compact[ref] = next_id
                all_node_locs[next_id] = locs[ref]
                next_id += 1

        # Walk the way: accumulate distance between intersection nodes
        seg_start_ref = refs[0]
        seg_dist = 0.0

        for k in range(1, len(refs)):
            prev_loc = locs[refs[k - 1]]
            curr_loc = locs[refs[k]]

            dlat = curr_loc[1] - prev_loc[1]
            dlon = curr_loc[0] - prev_loc[0]
            lat_mid = (curr_loc[1] + prev_loc[1]) / 2
            dx = dlon * 111.32 * np.cos(np.radians(lat_mid))
            dy = dlat * 111.32
            seg_dist += np.sqrt(dx * dx + dy * dy)

            # If this node is an intersection, emit an edge
            if refs[k] in intersection_nodes:
                u = osm_to_compact[seg_start_ref]
                v = osm_to_compact[refs[k]]
                if u != v and seg_dist > 0:
                    edges.append((u, v, seg_dist, surface_class))
                seg_start_ref = refs[k]
                seg_dist = 0.0

    n_nodes = next_id
    elapsed = time.time() - t0
    print(f"  Simplified graph: {n_nodes:,} nodes, {len(edges):,} edges")
    print(f"  Parsed and simplified in {elapsed:.1f}s")

    del handler
    return edges, all_node_locs, n_nodes


def build_adj_matrix(edges, n_nodes, cost_paved, cost_unpaved, cost_unknown):
    """
    Build sparse adjacency matrix from edge list with given cost multipliers.
    Uses numpy vectorized operations for speed.
    """
    cost_map = {"paved": cost_paved, "unpaved": cost_unpaved, "unknown": cost_unknown}

    print("  Building adjacency matrix...")
    t0 = time.time()

    # Convert to numpy arrays for speed
    us = np.array([e[0] for e in edges], dtype=np.int64)
    vs = np.array([e[1] for e in edges], dtype=np.int64)
    dists = np.array([e[2] for e in edges], dtype=np.float64)
    multipliers = np.array([cost_map.get(e[3], cost_unknown) for e in edges], dtype=np.float64)
    costs = dists * multipliers

    # Canonical edge ordering for dedup (smaller ID first)
    swap = us > vs
    u_canon = np.where(swap, vs, us)
    v_canon = np.where(swap, us, vs)

    # Deduplicate: keep minimum cost per edge using pandas
    import pandas as pd
    df = pd.DataFrame({"u": u_canon, "v": v_canon, "cost": costs})
    df_min = df.groupby(["u", "v"], sort=False)["cost"].min().reset_index()

    rows = np.concatenate([df_min["u"].values, df_min["v"].values])
    cols = np.concatenate([df_min["v"].values, df_min["u"].values])
    weights = np.concatenate([df_min["cost"].values, df_min["cost"].values])

    adj = coo_matrix((weights, (rows, cols)), shape=(n_nodes, n_nodes)).tocsr()

    # Connected components
    n_components, labels = connected_components(adj, directed=False)
    component_sizes = np.bincount(labels)
    largest = np.max(component_sizes)
    print(f"  Connected components: {n_components:,}")
    print(f"  Largest component: {largest:,} nodes ({100*largest/n_nodes:.1f}%)")

    elapsed = time.time() - t0
    print(f"  Matrix built in {elapsed:.1f}s")

    return adj, labels


def snap_centroids_to_graph(admin_gdf, node_coords):
    """
    For each admin centroid, find the nearest graph node.

    Returns: list of (admin_row_index, graph_node_id, distance_km)
    """
    print("Snapping admin centroids to road network...")

    # Build arrays of node coordinates for fast distance computation
    node_ids = np.array(list(node_coords.keys()))
    node_lons = np.array([node_coords[n][0] for n in node_ids])
    node_lats = np.array([node_coords[n][1] for n in node_ids])

    snapped = []
    for i in range(len(admin_gdf)):
        clon = admin_gdf.iloc[i]["centroid_lon"]
        clat = admin_gdf.iloc[i]["centroid_lat"]
        # Approximate distance in degrees (good enough for snapping)
        dists = np.sqrt((node_lons - clon)**2 + (node_lats - clat)**2)
        nearest_idx = np.argmin(dists)
        nearest_node = node_ids[nearest_idx]
        dist_deg = dists[nearest_idx]
        dist_km = dist_deg * 111.0
        snapped.append((i, int(nearest_node), dist_km))

    distances = [s[2] for s in snapped]
    print(f"  Snapped {len(snapped)} centroids")
    print(f"  Snap distance: mean={np.mean(distances):.1f} km, "
          f"max={np.max(distances):.1f} km, median={np.median(distances):.1f} km")

    return snapped


def compute_trade_costs(adj_matrix, source_nodes, n_graph_nodes):
    """
    Compute shortest path distances between all pairs of source nodes.

    Uses scipy's shortest_path with Dijkstra's algorithm.

    Returns: N×N numpy array where N = len(source_nodes)
    """
    n = len(source_nodes)
    print(f"Computing shortest paths for {n} nodes...")
    t0 = time.time()

    # Compute shortest paths from each source node
    # scipy shortest_path can compute from specific indices
    trade_costs = np.full((n, n), np.inf)

    for i, src in enumerate(source_nodes):
        if i % 20 == 0:
            print(f"  Processing node {i+1}/{n}...")
        # Single-source Dijkstra
        dist = shortest_path(adj_matrix, method='D', directed=False, indices=src)
        for j, dst in enumerate(source_nodes):
            trade_costs[i, j] = dist[dst]

    elapsed = time.time() - t0
    print(f"  Shortest paths computed in {elapsed:.1f}s")

    return trade_costs


# ── Main Pipeline ──────────────────────────────────────────────────────

def main():
    # ── Load admin boundaries ──
    print("Loading admin-2 boundaries...")
    admin = gpd.read_file(GADM_PATH, layer=GADM_LAYER)
    admin_proj = admin.to_crs("EPSG:32737")
    admin["centroid_lon"] = admin_proj.geometry.centroid.to_crs("EPSG:4326").x
    admin["centroid_lat"] = admin_proj.geometry.centroid.to_crs("EPSG:4326").y
    print(f"  {len(admin)} admin-2 units")

    # ── Parse PBF once and simplify to intersection graph ──
    print("\n── Parsing Road Network ──")
    edges, node_coords, n_nodes = parse_simplified_graph(PBF_PATH)

    # ── Build baseline adjacency matrix ──
    print("\n── Baseline Graph ──")
    adj_baseline, comp_labels = build_adj_matrix(
        edges, n_nodes, COST_PAVED, COST_UNPAVED, COST_UNKNOWN
    )

    # ── Build counterfactual (all paved) ──
    print("\n── Counterfactual Graph (all roads paved) ──")
    adj_counterfactual, _ = build_adj_matrix(
        edges, n_nodes, COST_PAVED, COST_PAVED, COST_PAVED
    )

    # ── Snap centroids ──
    snapped = snap_centroids_to_graph(admin, node_coords)
    source_nodes = [s[1] for s in snapped]  # graph node IDs

    # ── Compute trade costs ──
    print("\n── Baseline Trade Costs ──")
    tc_baseline = compute_trade_costs(adj_baseline, source_nodes, n_nodes)

    print("\n── Counterfactual Trade Costs ──")
    tc_counter = compute_trade_costs(adj_counterfactual, source_nodes, n_nodes)

    # ── Summary Statistics ──
    print("\n" + "=" * 70)
    print("TRADE COST SUMMARY")
    print("=" * 70)

    # Mask diagonal and infinities for stats
    mask = np.ones_like(tc_baseline, dtype=bool)
    np.fill_diagonal(mask, False)

    finite_baseline = tc_baseline[mask & np.isfinite(tc_baseline)]
    finite_counter = tc_counter[mask & np.isfinite(tc_counter)]

    n_pairs = len(source_nodes) * (len(source_nodes) - 1)
    n_connected = len(finite_baseline)
    n_disconnected = n_pairs - n_connected

    print(f"\nAdmin-2 units: {len(source_nodes)}")
    print(f"Total pairs: {n_pairs:,}")
    print(f"Connected pairs: {n_connected:,} ({100*n_connected/n_pairs:.1f}%)")
    print(f"Disconnected pairs: {n_disconnected:,} ({100*n_disconnected/n_pairs:.1f}%)")

    if len(finite_baseline) > 0:
        print(f"\nBaseline trade costs (weighted km):")
        print(f"  Mean:   {np.mean(finite_baseline):>8,.1f}")
        print(f"  Median: {np.median(finite_baseline):>8,.1f}")
        print(f"  Min:    {np.min(finite_baseline):>8,.1f}")
        print(f"  Max:    {np.max(finite_baseline):>8,.1f}")

        print(f"\nCounterfactual trade costs (all paved):")
        print(f"  Mean:   {np.mean(finite_counter):>8,.1f}")
        print(f"  Median: {np.median(finite_counter):>8,.1f}")
        print(f"  Min:    {np.min(finite_counter):>8,.1f}")
        print(f"  Max:    {np.max(finite_counter):>8,.1f}")

        # Reduction
        # Only compare pairs that are finite in both
        both_finite = mask & np.isfinite(tc_baseline) & np.isfinite(tc_counter)
        if both_finite.any():
            b = tc_baseline[both_finite]
            c = tc_counter[both_finite]
            pct_reduction = 100 * (1 - c / b)
            print(f"\nTrade cost reduction from paving:")
            print(f"  Mean reduction:   {np.mean(pct_reduction):>6.1f}%")
            print(f"  Median reduction: {np.median(pct_reduction):>6.1f}%")
            print(f"  Min reduction:    {np.min(pct_reduction):>6.1f}%")
            print(f"  Max reduction:    {np.max(pct_reduction):>6.1f}%")

    # ── Identify most/least connected units ──
    print("\n── Most Connected Admin-2 Units (lowest avg trade cost) ──")
    avg_costs = []
    for i in range(len(source_nodes)):
        row = tc_baseline[i, :]
        finite = row[np.isfinite(row) & (row > 0)]
        avg = np.mean(finite) if len(finite) > 0 else np.inf
        avg_costs.append(avg)

    sorted_idx = np.argsort(avg_costs)
    for rank, i in enumerate(sorted_idx[:10]):
        name = admin.iloc[snapped[i][0]]["NAME_2"]
        region = admin.iloc[snapped[i][0]]["NAME_1"]
        print(f"  {rank+1:2d}. {name:20s} ({region:15s})  avg cost: {avg_costs[i]:>8,.1f}")

    print("\n── Least Connected Admin-2 Units (highest avg trade cost) ──")
    for rank, i in enumerate(sorted_idx[-10:][::-1]):
        name = admin.iloc[snapped[i][0]]["NAME_2"]
        region = admin.iloc[snapped[i][0]]["NAME_1"]
        cost_str = f"{avg_costs[i]:>8,.1f}" if np.isfinite(avg_costs[i]) else "     inf"
        print(f"  {rank+1:2d}. {name:20s} ({region:15s})  avg cost: {cost_str}")

    # ── Save outputs ──
    print("\nSaving outputs...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Save admin with centroid info
    admin_out = admin.copy()
    admin_out["snap_node_id"] = [s[1] for s in snapped]
    admin_out["snap_distance_km"] = [s[2] for s in snapped]
    admin_out.to_file(ADMIN_OUTPUT, driver="GPKG")
    print(f"  Admin boundaries: {ADMIN_OUTPUT}")

    # Save trade cost matrices
    np.save(BASELINE_OUTPUT, tc_baseline)
    np.save(COUNTERFACTUAL_OUTPUT, tc_counter)
    print(f"  Baseline costs: {BASELINE_OUTPUT}")
    print(f"  Counterfactual costs: {COUNTERFACTUAL_OUTPUT}")

    # Save node names for reference
    names = [f"{admin.iloc[snapped[i][0]]['NAME_2']} ({admin.iloc[snapped[i][0]]['NAME_1']})"
             for i in range(len(source_nodes))]
    np.save(NODE_NAMES_OUTPUT, names)
    print(f"  Node names: {NODE_NAMES_OUTPUT}")

    print("\nDone.")


if __name__ == "__main__":
    main()
