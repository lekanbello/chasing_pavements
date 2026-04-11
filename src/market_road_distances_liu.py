"""
market_road_distances_liu.py — Compute market distances using Liu et al. road network.

Builds the road graph directly from Liu et al. (2026) shapefile instead of OSM.
This serves two purposes:
  1. Validation: compare distances with OSM-based graph (should be similar)
  2. Route decomposition: Liu has surface labels for every segment (no unknowns)

Also outputs the route decomposition (paved_km, unpaved_km) for each market pair,
enabling the Donaldson-style regression.

Usage:
    python3 src/market_road_distances_liu.py --country KEN
    python3 src/market_road_distances_liu.py --country TZA

Outputs:
    - data/processed/{country}_market_road_distances_liu.npy  (N×N total distance)
    - data/processed/{country}_route_decomposition.csv  (paved_km, unpaved_km per pair)
"""

import os
import sys
import time
import argparse
import heapq
import numpy as np
import pandas as pd
import geopandas as gpd
from collections import defaultdict
from scipy.sparse import csr_matrix, coo_matrix
from scipy.sparse.csgraph import connected_components

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from country_config import get_config_by_iso3

RTFP_PATH = 'data/raw/rtfp_prices.csv'

LIU_PATHS = {
    'KEN': 'data/raw/liu_et_al_kenya/Kenya/Kenya.shp',
    'TZA': 'data/raw/liu_et_al_tanzania/Tanzania/Tanzania.shp',
}


def build_graph_from_liu(liu_path):
    """
    Build a road network graph directly from Liu et al. shapefile.

    Each Liu segment becomes one or more edges. Nodes are created at
    segment start/end points. Segments sharing a start/end point
    (within tolerance) are connected at that node.
    """
    print(f"  Loading Liu et al. shapefile...")
    liu = gpd.read_file(liu_path)
    liu = liu.to_crs("EPSG:4326")
    print(f"  Segments: {len(liu):,}")

    # Extract edges from Liu segments
    print("  Extracting edges...")
    coord_to_id = {}
    node_coords = {}
    next_id = 0
    precision = 5  # ~1m snap tolerance

    edges = []  # (node_start, node_end, dist_km, surface)

    for idx, row in liu.iterrows():
        geom = row.geometry
        surface = row['Surface']  # 'paved' or 'unpaved'

        if geom.geom_type == 'MultiLineString':
            lines = list(geom.geoms)
        else:
            lines = [geom]

        for line in lines:
            coords = list(line.coords)
            if len(coords) < 2:
                continue

            # Create nodes at start and end
            start = (round(coords[0][0], precision), round(coords[0][1], precision))
            end = (round(coords[-1][0], precision), round(coords[-1][1], precision))

            for c in [start, end]:
                if c not in coord_to_id:
                    coord_to_id[c] = next_id
                    node_coords[next_id] = c
                    next_id += 1

            # Compute distance
            dist_km = 0
            for k in range(1, len(coords)):
                dlat = coords[k][1] - coords[k-1][1]
                dlon = coords[k][0] - coords[k-1][0]
                mid_lat = (coords[k][1] + coords[k-1][1]) / 2
                dx = dlon * 111.32 * np.cos(np.radians(mid_lat))
                dy = dlat * 111.32
                dist_km += np.sqrt(dx*dx + dy*dy)

            if dist_km > 0:
                u = coord_to_id[start]
                v = coord_to_id[end]
                if u != v:
                    edges.append((u, v, dist_km, surface))

        if idx % 100000 == 0 and idx > 0:
            print(f"    {idx:,} / {len(liu):,}...")

    n_nodes = next_id
    print(f"  Nodes: {n_nodes:,}, Edges: {len(edges):,}")

    # Deduplicate edges (keep minimum distance, preserve surface)
    edge_data = {}
    for u, v, dist, surface in edges:
        key = (min(u, v), max(u, v))
        if key not in edge_data or dist < edge_data[key]['dist']:
            edge_data[key] = {
                'dist': dist,
                'paved_km': dist if surface == 'paved' else 0.0,
                'unpaved_km': dist if surface == 'unpaved' else 0.0,
            }

    # Build sparse adjacency
    rows, cols, weights = [], [], []
    for (u, v), data in edge_data.items():
        rows.extend([u, v])
        cols.extend([v, u])
        weights.extend([data['dist'], data['dist']])

    adj = csr_matrix(
        (np.array(weights), (np.array(rows), np.array(cols))),
        shape=(n_nodes, n_nodes)
    )

    nc, labels = connected_components(adj, directed=False)
    sizes = np.bincount(labels)
    print(f"  Components: {nc:,}, Largest: {sizes.max():,} ({100*sizes.max()/n_nodes:.1f}%)")

    return adj, node_coords, edge_data


def dijkstra_decomposed(adj, edge_data, source, targets, n_nodes):
    """
    Dijkstra with path reconstruction and paved/unpaved decomposition.
    """
    dist = np.full(n_nodes, np.inf)
    pred = np.full(n_nodes, -1, dtype=np.int64)
    dist[source] = 0
    visited = np.zeros(n_nodes, dtype=bool)
    pq = [(0.0, source)]

    while pq:
        d, u = heapq.heappop(pq)
        if visited[u]:
            continue
        visited[u] = True

        row_start = adj.indptr[u]
        row_end = adj.indptr[u + 1]
        for idx in range(row_start, row_end):
            v = adj.indices[idx]
            w = adj.data[idx]
            if not visited[v] and d + w < dist[v]:
                dist[v] = d + w
                pred[v] = u
                heapq.heappush(pq, (dist[v], v))

    # Reconstruct paths and decompose
    results = {}
    for t in targets:
        if dist[t] == np.inf or t == source:
            results[t] = (np.inf, 0.0, 0.0)
            continue

        paved_km = 0.0
        unpaved_km = 0.0
        total_km = 0.0
        node = t
        while pred[node] != -1:
            p = pred[node]
            key = (min(p, node), max(p, node))
            if key in edge_data:
                paved_km += edge_data[key]['paved_km']
                unpaved_km += edge_data[key]['unpaved_km']
                total_km += edge_data[key]['dist']
            node = p

        results[t] = (total_km, paved_km, unpaved_km)

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", required=True, help="ISO3 code (KEN or TZA)")
    args = parser.parse_args()

    iso3 = args.country.upper()
    cfg = get_config_by_iso3(iso3)
    name_lower = cfg['country_name'].lower().replace(' ', '_').replace("'", "")

    print(f"\n{'=' * 60}")
    print(f"MARKET DISTANCES + ROUTE DECOMPOSITION (Liu et al.)")
    print(f"Country: {cfg['country_name']}")
    print(f"{'=' * 60}")

    liu_path = LIU_PATHS.get(iso3)
    if not liu_path or not os.path.exists(liu_path):
        print(f"ERROR: Liu et al. data not found: {liu_path}")
        return

    # Build graph
    print("\n1. Building graph from Liu et al....")
    t0 = time.time()
    adj, node_coords, edge_data = build_graph_from_liu(liu_path)
    print(f"  Built in {time.time()-t0:.1f}s")

    # Edge stats
    n_paved = sum(1 for d in edge_data.values() if d['paved_km'] > 0)
    n_unpaved = sum(1 for d in edge_data.values() if d['unpaved_km'] > 0)
    print(f"  Paved edges: {n_paved:,}, Unpaved edges: {n_unpaved:,}")

    # Load and snap markets
    print("\n2. Loading and snapping markets...")
    mkt_df = pd.read_csv(RTFP_PATH, usecols=['ISO3', 'mkt_name', 'lat', 'lon'])
    mkts = mkt_df[mkt_df['ISO3'] == iso3].drop_duplicates('mkt_name').dropna(subset=['lat', 'lon'])
    mkts = mkts.reset_index(drop=True)
    n_mkts = len(mkts)
    print(f"  Markets: {n_mkts}")

    if n_mkts == 0:
        print("  No markets found. Exiting.")
        return

    node_ids = np.array(list(node_coords.keys()))
    node_lons = np.array([node_coords[n][0] for n in node_ids])
    node_lats = np.array([node_coords[n][1] for n in node_ids])

    snap_nodes = []
    snap_dists = []
    for i in range(n_mkts):
        dists = np.sqrt((node_lons - mkts.iloc[i]['lon'])**2 +
                        (node_lats - mkts.iloc[i]['lat'])**2)
        nearest = np.argmin(dists)
        snap_nodes.append(int(node_ids[nearest]))
        snap_dists.append(dists[nearest] * 111.0)

    print(f"  Snap distance: mean={np.mean(snap_dists):.1f} km, "
          f"max={np.max(snap_dists):.1f} km")

    # Compute decomposed routes
    print(f"\n3. Computing decomposed shortest paths ({n_mkts} markets)...")
    t0 = time.time()
    n_nodes = adj.shape[0]

    road_dist = np.full((n_mkts, n_mkts), np.inf)
    route_rows = []

    for i in range(n_mkts):
        if i % 50 == 0:
            print(f"  Market {i+1}/{n_mkts}...")

        decomp = dijkstra_decomposed(adj, edge_data, snap_nodes[i], snap_nodes, n_nodes)

        for j in range(n_mkts):
            if i == j:
                continue
            total_km, paved_km, unpaved_km = decomp.get(snap_nodes[j], (np.inf, 0.0, 0.0))
            road_dist[i, j] = total_km

            if np.isfinite(total_km) and total_km > 0:
                route_rows.append({
                    'market_i': mkts.iloc[i]['mkt_name'],
                    'market_j': mkts.iloc[j]['mkt_name'],
                    'total_km': total_km,
                    'paved_km': paved_km,
                    'unpaved_km': unpaved_km,
                    'paved_share': paved_km / total_km,
                })

    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s")

    # Summary
    route_df = pd.DataFrame(route_rows)
    finite = np.isfinite(road_dist) & (road_dist > 0) & ~np.eye(n_mkts, dtype=bool)

    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Connected pairs: {finite.sum():,} / {n_mkts*(n_mkts-1):,} "
          f"({100*finite.sum()/(n_mkts*(n_mkts-1)):.1f}%)")
    if len(route_df) > 0:
        print(f"  Total km:   mean={route_df['total_km'].mean():.0f}, "
              f"median={route_df['total_km'].median():.0f}")
        print(f"  Paved km:   mean={route_df['paved_km'].mean():.0f}, "
              f"median={route_df['paved_km'].median():.0f}")
        print(f"  Unpaved km: mean={route_df['unpaved_km'].mean():.0f}, "
              f"median={route_df['unpaved_km'].median():.0f}")
        print(f"  Paved share: mean={route_df['paved_share'].mean():.3f}, "
              f"median={route_df['paved_share'].median():.3f}")

    # Save
    os.makedirs('data/processed', exist_ok=True)

    dist_path = f'data/processed/{name_lower}_market_road_distances_liu.npy'
    np.save(dist_path, road_dist)
    print(f"\n  Saved: {dist_path}")

    decomp_path = f'data/processed/{name_lower}_route_decomposition.csv'
    route_df.to_csv(decomp_path, index=False)
    print(f"  Saved: {decomp_path}")

    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
