"""
render_gmaps_figures.py — Render two figures for the deck from existing CSVs:

  1. outputs/figures/gmaps_speed_comparison.png — Tanzania single-panel
     (regenerated WITHOUT the connecting line per user feedback)

  2. outputs/figures/gmaps_speed_two_country.png — Tanzania + Kenya side by side
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

OUT = "outputs/figures"
os.makedirs(OUT, exist_ok=True)

PALETTE = {"paved": "#1f77b4", "unpaved": "#d62728"}


def render_single_panel(ax, df, title):
    same = df[df.same_road].copy()
    positions = {"paved": 0, "unpaved": 1}

    for surf in ["paved", "unpaved"]:
        sub = same[same.surface_class == surf]
        x = np.full(len(sub), positions[surf]) + np.random.uniform(-0.10, 0.10, len(sub))
        ax.scatter(x, sub.gmaps_speed_kmh, s=80, alpha=0.75,
                   color=PALETTE[surf], edgecolor="white", linewidth=1.2, zorder=3)

    box_data = [same[same.surface_class == s].gmaps_speed_kmh.values for s in ["paved", "unpaved"]]
    ax.boxplot(box_data, positions=[0, 1], widths=0.45, patch_artist=True,
               medianprops=dict(color="black", linewidth=2),
               boxprops=dict(facecolor="#eeeeee", edgecolor="#888888"),
               whiskerprops=dict(color="#888888"),
               capprops=dict(color="#888888"),
               flierprops=dict(marker=""), zorder=1)

    means = [same[same.surface_class == s].gmaps_speed_kmh.mean() for s in ["paved", "unpaved"]]
    ratio = means[0] / means[1] if means[1] else float("nan")

    # Annotate means at the side of each box (no connecting line)
    for pos, m in zip([0, 1], means):
        ax.annotate(f"{m:.0f} km/h", xy=(pos, m), xytext=(pos + 0.18, m),
                    fontsize=11, fontweight="bold", va="center")

    # Ratio callout
    ax.text(0.5, 95, f"Paved is {ratio:.2f}x faster",
            ha="center", fontsize=12, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#fff3cd", edgecolor="#856404"))

    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Paved", "Unpaved"], fontsize=12)
    ax.set_title(title, fontsize=12)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)


def render_tanzania_only():
    """Slide 14: same chart as before but with the connecting line removed."""
    df = pd.read_csv("outputs/gmaps_fellowship_queries.csv")
    fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=150)
    np.random.seed(1)
    render_single_panel(ax, df, title=(
        f"Google Maps travel speeds on Tanzanian road segments\n"
        f"{int((df.same_road).sum())} valid queries (length-matched routes only)"))
    ax.set_ylabel("Travel speed (km/h)", fontsize=12)
    ax.set_ylim(35, 105)
    plt.tight_layout()
    out = f"{OUT}/gmaps_speed_comparison.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def render_two_country():
    """New slide: Tanzania | Kenya side by side, common y-axis."""
    tz = pd.read_csv("outputs/gmaps_fellowship_queries.csv")
    kn = pd.read_csv("outputs/gmaps_kenya_queries.csv")

    # Compute pooled headline
    pooled_p = pd.concat([
        tz[(tz.surface_class == "paved") & tz.same_road].gmaps_speed_kmh,
        kn[(kn.surface_class == "paved") & kn.same_road].gmaps_speed_kmh,
    ])
    pooled_u = pd.concat([
        tz[(tz.surface_class == "unpaved") & tz.same_road].gmaps_speed_kmh,
        kn[(kn.surface_class == "unpaved") & kn.same_road].gmaps_speed_kmh,
    ])
    pooled_ratio = pooled_p.mean() / pooled_u.mean()
    n_total = len(pooled_p) + len(pooled_u)
    print(f"Pooled: paved {pooled_p.mean():.1f} (n={len(pooled_p)}), "
          f"unpaved {pooled_u.mean():.1f} (n={len(pooled_u)}), ratio {pooled_ratio:.2f}x")

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.0), dpi=150, sharey=True)
    np.random.seed(1)
    render_single_panel(axes[0], tz, title="Tanzania")
    render_single_panel(axes[1], kn, title="Kenya")
    axes[0].set_ylabel("Travel speed (km/h)", fontsize=12)
    axes[0].set_ylim(35, 110)

    fig.suptitle(
        f"Paved roads are faster on the same segments — in both countries.\n"
        f"Pooled across {n_total} length-matched queries: paved is {pooled_ratio:.2f}x faster.",
        fontsize=12, y=1.00,
    )

    plt.tight_layout()
    out = f"{OUT}/gmaps_speed_two_country.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


if __name__ == "__main__":
    render_tanzania_only()
    render_two_country()
