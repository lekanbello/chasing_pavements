"""
market_road_distances.py — Compute bilateral road distances between RTFP markets.

Builds the road network graph from OSM PBF, snaps market locations to the
nearest graph node, and runs Dijkstra's to get road distances between all
market pairs. These distances are used in the price-distance regression
to estimate trade costs.

Usage:
    python3 src/market_road_distances.py --country KEN
    python3 src/market_road_distances.py --country TZA

Requires:
    - OSM PBF in data/raw/
    - RTFP market data (hardcoded path for now)

Outputs:
    - data/processed/{country}_market_road_distances.npy (N×N matrix)
    - data/processed/{country}_market_locations.csv (market names + coords)
"""

import os
import sys
import time
import argparse
import numpy as np
import pandas as pd
import osmium
from collections import defaultdict
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import shortest_path, connected_components

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from country_config import get_config_by_iso3

RTFP_PATH = ('/Users/olalekanbello/Dropbox/Nigeria Exchange Rate Shared/'
             '_Essential_Files/Nigeria_Revised_Paper_JIE/Data/World Bank/'
             'WLD_RTFP_mkt_2026-03-24.csv')

ROAD_CLASSES = {
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link", "unclassified", "residential", "track",
}


class GraphHandler(osmium.SimpleHandler):
    """Extract road network topology with distance weights."""

    def __init__(self):
        super().__init__()
        self.edges = []
        self.node_locs = {}

    def way(self, w):
        hw = w.tags.get("highway")
        if hw not in ROAD_CLASSES:
            return
        try:
            nodes = [(n.ref, n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(nodes) < 2:
            return
        for ref, lon, lat in nodes:
            self.node_locs[ref] = (lon, lat)
        for k in range(1, len(nodes)):
            r0, lo0, la0 = nodes[k - 1]
            r1, lo1, la1 = nodes[k]
            dlat, dlon = la1 - la0, lo1 - lo0
            mid = (la1 + la0) / 2
            dx = dlon * 111.32 * np.cos(np.radians(mid))
            dy = dlat * 111.32
            dist = np.sqrt(dx * dx + dy * dy)
            if dist > 0 and r0 != r1:
                self.edges.append((r0, r1, dist))


def build_graph(pbf_path):
    """Build sparse adjacency matrix from OSM PBF."""
    print(f"  Parsing {os.path.basename(pbf_path)}...")
    t0 = time.time()

    handler = GraphHandler()
    handler.apply_file(pbf_path, locations=True)
    print(f"  Edges: {len(handler.edges):,}, Nodes: {len(handler.node_locs):,}")

    osm_to_id = {ref: i for i, ref in enumerate(handler.node_locs)}
    n_nodes = len(osm_to_id)
    node_coords = {osm_to_id[r]: loc for r, loc in handler.node_locs.items()}

    # Deduplicate edges (keep minimum distance)
    edge_min = defaultdict(lambda: float('inf'))
    for s, e, dist in handler.edges:
        u, v = osm_to_id[s], osm_to_id[e]
        key = (min(u, v), max(u, v))
        if dist < edge_min[key]:
            edge_min[key] = dist

    rows, cols, weights = [], [], []
    for (u, v), w in edge_min.items():
        rows.extend([u, v])
        cols.extend([v, u])
        weights.extend([w, w])

    adj = coo_matrix(
        (np.array(weights), (np.array(rows), np.array(cols))),
        shape=(n_nodes, n_nodes)
    ).tocsr()

    nc, labels = connected_components(adj, directed=False)
    sizes = np.bincount(labels)
    print(f"  Components: {nc:,}, Largest: {sizes.max():,} ({100 * sizes.max() / n_nodes:.1f}%)")
    print(f"  Built in {time.time() - t0:.1f}s")

    del handler
    return node_coords, adj


def load_markets(iso3):
    """Load RTFP market locations for a country."""
    df = pd.read_csv(RTFP_PATH, usecols=['ISO3', 'mkt_name', 'lat', 'lon'])
    mkts = df[df['ISO3'] == iso3].drop_duplicates('mkt_name').dropna(subset=['lat', 'lon'])
    mkts = mkts.reset_index(drop=True)
    print(f"  RTFP markets for {iso3}: {len(mkts)}")
    return mkts


def snap_markets(mkts, node_coords):
    """Snap each market to nearest graph node."""
    node_ids = np.array(list(node_coords.keys()))
    node_lons = np.array([node_coords[n][0] for n in node_ids])
    node_lats = np.array([node_coords[n][1] for n in node_ids])

    snap_nodes = []
    snap_dists = []
    for i in range(len(mkts)):
        dists = np.sqrt((node_lons - mkts.iloc[i]['lon']) ** 2 +
                        (node_lats - mkts.iloc[i]['lat']) ** 2)
        nearest = np.argmin(dists)
        snap_nodes.append(int(node_ids[nearest]))
        snap_dists.append(dists[nearest] * 111.0)

    print(f"  Snap distance: mean={np.mean(snap_dists):.1f} km, "
          f"max={np.max(snap_dists):.1f} km, median={np.median(snap_dists):.1f} km")
    return snap_nodes


def compute_distances(adj, snap_nodes, n_mkts):
    """Run Dijkstra from each market to all others."""
    print(f"  Computing shortest paths for {n_mkts} markets...")
    t0 = time.time()
    road_dist = np.full((n_mkts, n_mkts), np.inf)

    for i in range(n_mkts):
        if i % 50 == 0:
            print(f"    Market {i + 1}/{n_mkts}...")
        d = shortest_path(adj, method='D', directed=False, indices=snap_nodes[i])
        for j in range(n_mkts):
            road_dist[i, j] = d[snap_nodes[j]]

    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s")
    return road_dist


def main():
    parser = argparse.ArgumentParser(description="Compute market-to-market road distances")
    parser.add_argument("--country", required=True, help="ISO3 country code")
    args = parser.parse_args()

    iso3 = args.country.upper()
    cfg = get_config_by_iso3(iso3)
    name_lower = cfg['country_name'].lower().replace(' ', '_').replace("'", "")

    print(f"\n{'=' * 60}")
    print(f"MARKET ROAD DISTANCES: {cfg['country_name']}")
    print(f"{'=' * 60}")

    # Build graph
    print("\nBuilding road graph...")
    pbf = cfg['osm_pbf']
    if not os.path.exists(pbf):
        import subprocess
        url = cfg.get('osm_pbf_url', f"https://download.geofabrik.de/africa/{os.path.basename(pbf)}")
        print(f"  Downloading {os.path.basename(pbf)}...")
        subprocess.run(["curl", "-L", "-o", pbf, url], check=True)

    node_coords, adj = build_graph(pbf)

    # Load and snap markets
    print("\nLoading markets...")
    mkts = load_markets(iso3)
    if len(mkts) == 0:
        print(f"  No RTFP markets found for {iso3}. Exiting.")
        return

    print("\nSnapping to graph...")
    snap_nodes = snap_markets(mkts, node_coords)

    # Compute distances
    print("\nComputing distances...")
    road_dist = compute_distances(adj, snap_nodes, len(mkts))

    # Summary
    finite = np.isfinite(road_dist) & (road_dist > 0) & ~np.eye(len(mkts), dtype=bool)
    n_pairs = len(mkts) * (len(mkts) - 1)
    print(f"\n  Connected pairs: {finite.sum():,} / {n_pairs:,} "
          f"({100 * finite.sum() / n_pairs:.1f}%)")
    if finite.any():
        print(f"  Road distance: min={road_dist[finite].min():.0f} km, "
              f"median={np.median(road_dist[finite]):.0f} km, "
              f"max={road_dist[finite].max():.0f} km")

    # Save
    out_dist = f'data/processed/{name_lower}_market_road_distances.npy'
    out_mkts = f'data/processed/{name_lower}_market_locations.csv'
    os.makedirs('data/processed', exist_ok=True)
    np.save(out_dist, road_dist)
    mkts[['mkt_name', 'lat', 'lon']].to_csv(out_mkts, index=False)
    print(f"\n  Saved: {out_dist}")
    print(f"  Saved: {out_mkts}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
