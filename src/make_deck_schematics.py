"""
make_deck_schematics.py — three matplotlib schematics for the fellowship deck.

Outputs:
  outputs/figures/schematic_network.png   (slide 3 — network ripple effects)
  outputs/figures/schematic_method_loop.png (slide 4 — prices / production / people)
  outputs/figures/schematic_priority.png    (slide 17 — priority paving)
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Circle

OUT = "outputs/figures"
os.makedirs(OUT, exist_ok=True)


# ---------------------------------------------------------------------------
# Slide 3 — "Why this is a network problem"
# 5 nodes connected by roads. Highlight one paved edge; arrows show price
# changes propagating to non-adjacent nodes.
# ---------------------------------------------------------------------------
def schematic_network():
    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)

    # Node positions (loose pentagonal layout)
    nodes = {
        "A": (1.0, 3.0),
        "B": (3.0, 4.5),
        "C": (5.5, 3.0),
        "D": (4.0, 1.0),
        "E": (1.5, 1.0),
    }
    edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"), ("E", "A"),
             ("A", "C"), ("B", "D")]
    paved = ("A", "B")  # the road that gets upgraded

    # Draw all edges first (gray), then the highlighted one
    for u, v in edges:
        x1, y1 = nodes[u]; x2, y2 = nodes[v]
        if (u, v) == paved or (v, u) == paved:
            ax.plot([x1, x2], [y1, y2], color="#1f77b4", linewidth=5, zorder=2)
        else:
            ax.plot([x1, x2], [y1, y2], color="#888888", linewidth=2, linestyle="--",
                    zorder=1, alpha=0.7)

    # Nodes
    for name, (x, y) in nodes.items():
        circ = Circle((x, y), 0.32, facecolor="white", edgecolor="black",
                      linewidth=1.6, zorder=3)
        ax.add_patch(circ)
        ax.text(x, y, name, ha="center", va="center", fontsize=14,
                fontweight="bold", zorder=4)

    # Ripple arrows: A-B paved -> prices change in C, D, E
    for target in ["C", "D", "E"]:
        x1, y1 = nodes["B"]
        x2, y2 = nodes[target]
        # nudge so arrow doesn't sit on top of the existing edge
        midx = (x1 + x2) / 2 + (0.2 if target != "C" else 0)
        midy = (y1 + y2) / 2 + 0.4
        arr = FancyArrowPatch(
            (x1, y1), (x2, y2),
            connectionstyle="arc3,rad=0.25",
            arrowstyle="->", color="#d62728", linewidth=1.6,
            mutation_scale=18, zorder=5, alpha=0.85,
        )
        ax.add_patch(arr)

    ax.text(2.0, 4.0, "Newly paved", color="#1f77b4", fontsize=12,
            fontweight="bold", rotation=35)
    ax.text(5.6, 4.2, "Prices change\nfar from the road",
            color="#d62728", fontsize=11, ha="left", fontweight="bold")

    ax.set_xlim(-0.2, 7.5)
    ax.set_ylim(0.0, 5.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("A change in one place ripples through the whole network",
                 fontsize=13, pad=12)

    plt.tight_layout()
    out = f"{OUT}/schematic_network.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


# ---------------------------------------------------------------------------
# Slide 4 — "How spatial trade models think about this"
# Three boxes: Prices, Production, People — with mutual feedback arrows.
# A "Roads" box on the side feeding into all three.
# ---------------------------------------------------------------------------
def schematic_method_loop():
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=150)

    boxes = {
        "Roads":       (1.0, 2.5, "#444444",  "white"),
        "Prices":      (4.5, 4.0, "#1f77b4",  "white"),
        "Production":  (4.5, 1.0, "#2ca02c",  "white"),
        "People":      (8.0, 2.5, "#ff7f0e",  "white"),
    }
    box_w, box_h = 1.8, 0.9

    for name, (x, y, fc, tc) in boxes.items():
        b = FancyBboxPatch(
            (x - box_w/2, y - box_h/2), box_w, box_h,
            boxstyle="round,pad=0.05,rounding_size=0.15",
            facecolor=fc, edgecolor="black", linewidth=1.4, zorder=2)
        ax.add_patch(b)
        ax.text(x, y, name, ha="center", va="center",
                fontsize=14, fontweight="bold", color=tc, zorder=3)

    def arrow(a, b, rad=0.0, color="black", style="->"):
        x1, y1 = boxes[a][:2]; x2, y2 = boxes[b][:2]
        arr = FancyArrowPatch(
            (x1, y1), (x2, y2),
            connectionstyle=f"arc3,rad={rad}",
            arrowstyle=style, color=color, linewidth=1.5,
            mutation_scale=16, zorder=1,
            shrinkA=28, shrinkB=28,
        )
        ax.add_patch(arr)

    # Roads -> the three middle boxes (one-way drivers)
    arrow("Roads", "Prices",     rad=0.12, color="#444444")
    arrow("Roads", "Production", rad=-0.12, color="#444444")
    arrow("Roads", "People",     rad=0.0, color="#444444")

    # Mutual feedback among the three core boxes
    arrow("Prices", "Production", rad=0.18, color="#1f77b4")
    arrow("Production", "Prices", rad=0.18, color="#2ca02c")
    arrow("Prices", "People",     rad=-0.18, color="#1f77b4")
    arrow("People", "Prices",     rad=-0.18, color="#ff7f0e")
    arrow("Production", "People", rad=0.18, color="#2ca02c")
    arrow("People", "Production", rad=0.18, color="#ff7f0e")

    # Annotations
    ax.text(4.5, 5.1, "What people pay", ha="center", fontsize=10, color="#1f77b4",
            fontstyle="italic")
    ax.text(4.5, -0.2, "What regions make", ha="center", fontsize=10, color="#2ca02c",
            fontstyle="italic")
    ax.text(8.0, 1.5, "Where workers live", ha="center", fontsize=10, color="#ff7f0e",
            fontstyle="italic")
    ax.text(1.0, 1.4, "Surface, length,\nconnectivity",
            ha="center", fontsize=10, color="#444444", fontstyle="italic")

    ax.set_xlim(-0.2, 9.6)
    ax.set_ylim(-0.6, 5.6)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("All three adjust together until everything settles",
                 fontsize=13, pad=10)

    plt.tight_layout()
    out = f"{OUT}/schematic_method_loop.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


# ---------------------------------------------------------------------------
# Slide 17 — "Optimal paving on a budget"
# Network with edges colored by gain-per-dollar; top-3 highlighted.
# ---------------------------------------------------------------------------
def schematic_priority():
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=150)

    np.random.seed(11)
    # Random-ish set of 8 nodes
    pts = np.array([
        [1.0, 3.5], [2.5, 5.0], [3.5, 3.5], [5.0, 5.0],
        [5.5, 2.5], [3.0, 1.0], [1.5, 1.5], [6.5, 3.5],
    ])
    # Edges: a few hand-picked plus random
    edges = [(0,1),(0,2),(1,3),(2,3),(2,4),(3,7),(4,7),(4,5),(5,6),(0,6),(2,5),(1,2)]

    # Assign a "gain-per-dollar" score to each
    scores = np.random.uniform(0.1, 1.0, len(edges))
    order = np.argsort(-scores)
    top3 = set(order[:3])

    cmap = plt.cm.YlOrRd
    for i, (u, v) in enumerate(edges):
        x1, y1 = pts[u]; x2, y2 = pts[v]
        if i in top3:
            ax.plot([x1, x2], [y1, y2], color="#d62728", linewidth=5, zorder=3)
        else:
            ax.plot([x1, x2], [y1, y2], color=cmap(scores[i] * 0.7),
                    linewidth=2.5, zorder=2, alpha=0.7)

    for x, y in pts:
        c = Circle((x, y), 0.16, facecolor="white", edgecolor="black",
                   linewidth=1.4, zorder=4)
        ax.add_patch(c)

    # Legend / labels
    ax.text(4.5, 5.6, "Top 3 segments by welfare gain per dollar",
            ha="center", color="#d62728", fontsize=12, fontweight="bold")

    # Color-bar-ish bar
    ax.text(7.2, 4.8, "Lower priority", color="#cccc66", fontsize=9, ha="left")
    ax.text(7.2, 5.2, "Higher priority", color="#d62728", fontsize=9, ha="left",
            fontweight="bold")

    ax.set_xlim(0.2, 8.0)
    ax.set_ylim(0.2, 6.0)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("From 'pave everything' to 'pave the right things first'",
                 fontsize=13, pad=10)

    plt.tight_layout()
    out = f"{OUT}/schematic_priority.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


if __name__ == "__main__":
    schematic_network()
    schematic_method_loop()
    schematic_priority()
