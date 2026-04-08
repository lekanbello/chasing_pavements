"""
viz_trade.py — Visualize trade cost results from network.py.

Produces:
  1. Choropleth map: average trade cost reduction by district
  2. Scatter: baseline vs counterfactual trade costs for all connected pairs
  3. Distribution of trade cost reductions
  4. Bar chart: most and least connected districts
  5. Map: connected vs disconnected districts
"""

import os
import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Patch

# ── Configuration ──────────────────────────────────────────────────────

ADMIN_PATH = "data/processed/tanzania_admin2.gpkg"
BASELINE_PATH = "data/processed/tanzania_trade_costs_baseline.npy"
COUNTERFACTUAL_PATH = "data/processed/tanzania_trade_costs_counterfactual.npy"
NAMES_PATH = "data/processed/tanzania_admin2_names.npy"
FIG_DIR = "outputs/figures"


def load_data():
    admin = gpd.read_file(ADMIN_PATH)
    tc_base = np.load(BASELINE_PATH)
    tc_cf = np.load(COUNTERFACTUAL_PATH)
    names = np.load(NAMES_PATH, allow_pickle=True)
    return admin, tc_base, tc_cf, names


def compute_district_stats(tc_base, tc_cf):
    """Compute per-district average trade costs and reductions."""
    n = tc_base.shape[0]
    avg_baseline = np.full(n, np.nan)
    avg_counterfactual = np.full(n, np.nan)
    avg_reduction_pct = np.full(n, np.nan)
    n_connected = np.zeros(n, dtype=int)

    for i in range(n):
        mask = np.isfinite(tc_base[i, :]) & (np.arange(n) != i)
        n_connected[i] = mask.sum()
        if mask.sum() > 0:
            avg_baseline[i] = np.mean(tc_base[i, mask])
            avg_counterfactual[i] = np.mean(tc_cf[i, mask])
            reductions = 100 * (1 - tc_cf[i, mask] / tc_base[i, mask])
            avg_reduction_pct[i] = np.mean(reductions)

    return avg_baseline, avg_counterfactual, avg_reduction_pct, n_connected


# ── Plot 1: Choropleth of trade cost reduction ────────────────────────

def plot_reduction_map(admin, avg_reduction_pct, fig_dir):
    """Choropleth map showing average trade cost reduction per district."""
    print("Plotting trade cost reduction map...")

    admin_plot = admin.copy()
    admin_plot["reduction_pct"] = avg_reduction_pct

    fig, ax = plt.subplots(1, 1, figsize=(12, 14))

    # Plot districts with data
    has_data = ~np.isnan(avg_reduction_pct)
    admin_plot[~has_data].plot(ax=ax, color="#d9d9d9", edgecolor="white", linewidth=0.3)
    admin_plot[has_data].plot(
        ax=ax, column="reduction_pct", cmap="RdYlGn", edgecolor="white",
        linewidth=0.3, legend=True,
        legend_kwds={"label": "Avg Trade Cost Reduction (%)", "shrink": 0.6},
        vmin=0, vmax=50,
    )

    ax.set_title("Trade Cost Reduction from Paving All Roads\nTanzania, by District",
                 fontsize=14, fontweight="bold")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")

    # Add annotation
    valid = avg_reduction_pct[~np.isnan(avg_reduction_pct)]
    info = (f"Mean reduction: {np.mean(valid):.1f}%\n"
            f"Median: {np.median(valid):.1f}%\n"
            f"Range: {np.min(valid):.1f}% - {np.max(valid):.1f}%\n"
            f"Districts with data: {has_data.sum()} / {len(admin)}\n"
            f"Gray = disconnected")
    ax.text(0.98, 0.02, info, transform=ax.transAxes,
            fontsize=9, verticalalignment="bottom", horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.9))

    plt.tight_layout()
    path = os.path.join(fig_dir, "tanzania_trade_cost_reduction_map.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


# ── Plot 2: Baseline vs Counterfactual scatter ────────────────────────

def plot_scatter(tc_base, tc_cf, fig_dir):
    """Scatter plot of baseline vs counterfactual trade costs for all pairs."""
    print("Plotting baseline vs counterfactual scatter...")

    n = tc_base.shape[0]
    mask = np.ones((n, n), dtype=bool)
    np.fill_diagonal(mask, False)
    both_finite = mask & np.isfinite(tc_base) & np.isfinite(tc_cf)

    b = tc_base[both_finite]
    c = tc_cf[both_finite]

    fig, ax = plt.subplots(figsize=(10, 10))
    ax.scatter(b, c, s=1, alpha=0.15, color="#2166ac", rasterized=True)

    # 45-degree line
    max_val = max(b.max(), c.max())
    ax.plot([0, max_val], [0, max_val], 'k--', alpha=0.5, linewidth=1, label="No change")

    # Mean reduction line
    mean_ratio = np.mean(c / b)
    ax.plot([0, max_val], [0, max_val * mean_ratio], color="#b2182b",
            linewidth=1.5, alpha=0.8, label=f"Mean ratio: {mean_ratio:.2f}")

    ax.set_xlabel("Baseline Trade Cost (weighted km)", fontsize=12)
    ax.set_ylabel("Counterfactual Trade Cost (all paved)", fontsize=12)
    ax.set_title("Bilateral Trade Costs: Baseline vs. All-Paved Counterfactual\n"
                 "Tanzania, 186 Admin-2 Districts", fontsize=13, fontweight="bold")
    ax.legend(fontsize=11)
    ax.set_aspect("equal")
    ax.set_xlim(0, max_val * 1.05)
    ax.set_ylim(0, max_val * 1.05)

    info = (f"Connected pairs: {both_finite.sum():,}\n"
            f"Mean baseline: {np.mean(b):,.0f} km\n"
            f"Mean counterfactual: {np.mean(c):,.0f} km\n"
            f"Mean reduction: {100*(1-mean_ratio):.1f}%")
    ax.text(0.02, 0.98, info, transform=ax.transAxes,
            fontsize=10, verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.9))

    plt.tight_layout()
    path = os.path.join(fig_dir, "tanzania_trade_cost_scatter.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


# ── Plot 3: Distribution of trade cost reductions ─────────────────────

def plot_reduction_distribution(tc_base, tc_cf, fig_dir):
    """Histogram of pairwise trade cost reductions."""
    print("Plotting reduction distribution...")

    n = tc_base.shape[0]
    mask = np.ones((n, n), dtype=bool)
    np.fill_diagonal(mask, False)
    both_finite = mask & np.isfinite(tc_base) & np.isfinite(tc_cf) & (tc_base > 0)

    reductions = 100 * (1 - tc_cf[both_finite] / tc_base[both_finite])

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(reductions, bins=80, color="#4393c3", edgecolor="white", alpha=0.9)
    ax.axvline(np.mean(reductions), color="#b2182b", linestyle="--", linewidth=2,
               label=f"Mean: {np.mean(reductions):.1f}%")
    ax.axvline(np.median(reductions), color="#d6604d", linestyle=":", linewidth=2,
               label=f"Median: {np.median(reductions):.1f}%")

    ax.set_xlabel("Trade Cost Reduction (%)", fontsize=12)
    ax.set_ylabel("Number of District Pairs", fontsize=12)
    ax.set_title("Distribution of Bilateral Trade Cost Reductions from Full Paving\n"
                 "Tanzania, All Connected District Pairs", fontsize=13, fontweight="bold")
    ax.legend(fontsize=11)

    plt.tight_layout()
    path = os.path.join(fig_dir, "tanzania_reduction_distribution.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


# ── Plot 4: Top/bottom districts bar chart ────────────────────────────

def plot_district_rankings(admin, avg_reduction_pct, names, fig_dir):
    """Bar chart of districts with highest and lowest trade cost reductions."""
    print("Plotting district rankings...")

    valid_mask = ~np.isnan(avg_reduction_pct)
    valid_idx = np.where(valid_mask)[0]
    valid_reductions = avg_reduction_pct[valid_mask]
    valid_names = names[valid_mask]

    sorted_idx = np.argsort(valid_reductions)

    # Top 15 and bottom 15
    top_n = 15
    top_idx = sorted_idx[-top_n:][::-1]
    bottom_idx = sorted_idx[:top_n]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))

    # Highest reductions (most to gain from paving)
    ax1.barh(range(top_n), valid_reductions[top_idx], color="#b2182b", edgecolor="white")
    ax1.set_yticks(range(top_n))
    ax1.set_yticklabels([valid_names[i] for i in top_idx], fontsize=9)
    ax1.invert_yaxis()
    ax1.set_xlabel("Avg Trade Cost Reduction (%)")
    ax1.set_title("Most to Gain from Paving", fontweight="bold")
    ax1.set_xlim(0, max(valid_reductions) * 1.1)

    # Lowest reductions (least to gain — already well-connected)
    ax2.barh(range(top_n), valid_reductions[bottom_idx], color="#2166ac", edgecolor="white")
    ax2.set_yticks(range(top_n))
    ax2.set_yticklabels([valid_names[i] for i in bottom_idx], fontsize=9)
    ax2.invert_yaxis()
    ax2.set_xlabel("Avg Trade Cost Reduction (%)")
    ax2.set_title("Least to Gain (Already Well-Connected)", fontweight="bold")
    ax2.set_xlim(0, max(valid_reductions) * 1.1)

    fig.suptitle("Districts Ranked by Trade Cost Reduction from Paving\nTanzania",
                 fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    path = os.path.join(fig_dir, "tanzania_district_rankings.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


# ── Plot 5: Connectivity map ──────────────────────────────────────────

def plot_connectivity_map(admin, n_connected, fig_dir):
    """Map showing number of connected districts for each unit."""
    print("Plotting connectivity map...")

    admin_plot = admin.copy()
    admin_plot["n_connected"] = n_connected

    fig, ax = plt.subplots(1, 1, figsize=(12, 14))

    disconnected = n_connected == 0
    admin_plot[disconnected].plot(ax=ax, color="#d9d9d9", edgecolor="white", linewidth=0.3)
    admin_plot[~disconnected].plot(
        ax=ax, column="n_connected", cmap="YlOrRd", edgecolor="white",
        linewidth=0.3, legend=True,
        legend_kwds={"label": "Number of Connected Districts", "shrink": 0.6},
    )

    ax.set_title("Road Network Connectivity by District\nTanzania",
                 fontsize=14, fontweight="bold")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")

    info = (f"Fully connected: {(~disconnected).sum()} / {len(admin)}\n"
            f"Disconnected: {disconnected.sum()} (gray)\n"
            f"Max connections: {n_connected.max()}")
    ax.text(0.98, 0.02, info, transform=ax.transAxes,
            fontsize=9, verticalalignment="bottom", horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.9))

    plt.tight_layout()
    path = os.path.join(fig_dir, "tanzania_connectivity_map.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


# ── Main ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(FIG_DIR, exist_ok=True)
    admin, tc_base, tc_cf, names = load_data()
    avg_baseline, avg_cf, avg_reduction, n_connected = compute_district_stats(tc_base, tc_cf)

    plot_reduction_map(admin, avg_reduction, FIG_DIR)
    plot_scatter(tc_base, tc_cf, FIG_DIR)
    plot_reduction_distribution(tc_base, tc_cf, FIG_DIR)
    plot_district_rankings(admin, avg_reduction, names, FIG_DIR)
    plot_connectivity_map(admin, n_connected, FIG_DIR)

    print("\nDone. All figures saved to outputs/figures/")
