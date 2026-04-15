#!/usr/bin/env python
"""Generate a clean architecture diagram image for the FYP poster."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


def add_box(ax, x, y, w, h, text, fc, ec="#0f172a", fs=12, weight="bold"):
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.02",
        linewidth=2.0,
        edgecolor=ec,
        facecolor=fc,
    )
    ax.add_patch(box)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, weight=weight, color="#0f172a")


def add_arrow(ax, x1, y1, x2, y2, color="#334155", lw=1.8, style="-|>"):
    arrow = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=14, linewidth=lw, color=color)
    ax.add_patch(arrow)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "reports" / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "poster_architecture_diagram.png"

    fig, ax = plt.subplots(figsize=(14, 8), dpi=220)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Title
    ax.text(
        0.5,
        0.965,
        "Three-Layer Decentralized Smart Device Architecture",
        ha="center",
        va="center",
        fontsize=18,
        weight="bold",
        color="#0b132b",
    )
    ax.text(
        0.5,
        0.93,
        "Hubless peer-to-peer coordination via Swarm Engine",
        ha="center",
        va="center",
        fontsize=11,
        color="#334155",
    )

    # Layer strips
    add_box(ax, 0.06, 0.72, 0.88, 0.16, "User Layer", fc="#e0ecff", fs=13)
    add_box(ax, 0.06, 0.40, 0.88, 0.26, "Swarm Engine Layer", fc="#dbf5f0", fs=13)
    add_box(ax, 0.06, 0.12, 0.88, 0.20, "Device Layer", fc="#fff0df", fs=13)

    # User layer box
    add_box(
        ax,
        0.30,
        0.755,
        0.40,
        0.09,
        "Web Dashboard\nMonitoring • Alerts • Manual Override",
        fc="#f8fbff",
        fs=11,
    )

    # Engine nodes
    nodes = {
        "Node A": (0.18, 0.48),
        "Node B": (0.39, 0.48),
        "Node C": (0.60, 0.48),
        "Node D": (0.81, 0.48),
    }
    node_w, node_h = 0.13, 0.11
    for label, (cx, cy) in nodes.items():
        add_box(ax, cx - node_w / 2, cy - node_h / 2, node_w, node_h, label, fc="#f3fffd", fs=10)

    # Engine mesh connections
    node_centers = {k: v for k, v in nodes.items()}
    mesh_pairs = [
        ("Node A", "Node B"),
        ("Node B", "Node C"),
        ("Node C", "Node D"),
        ("Node A", "Node D"),
        ("Node A", "Node C"),
        ("Node B", "Node D"),
    ]
    for a, b in mesh_pairs:
        xa, ya = node_centers[a]
        xb, yb = node_centers[b]
        add_arrow(ax, xa, ya, xb, yb, color="#0f766e", lw=1.6, style="<->")

    # Device layer boxes
    add_box(ax, 0.14, 0.165, 0.26, 0.11, "Sensors\nTemperature • Motion • Light", fc="#fffaf4", fs=10)
    add_box(ax, 0.60, 0.165, 0.26, 0.11, "Actuators\nRelay • Fan • Light", fc="#fffaf4", fs=10)

    # Vertical data flow arrows
    for n in ("Node A", "Node B"):
        x, y = node_centers[n]
        add_arrow(ax, 0.27, 0.275, x, y - 0.07, color="#334155", lw=1.8)
    for n in ("Node C", "Node D"):
        x, y = node_centers[n]
        add_arrow(ax, x, y - 0.07, 0.73, 0.275, color="#334155", lw=1.8)

    # Dashboard interaction
    add_arrow(ax, 0.50, 0.755, node_centers["Node B"][0], node_centers["Node B"][1] + 0.07, color="#1d4ed8", lw=2.0, style="<->")
    add_arrow(ax, 0.50, 0.755, node_centers["Node C"][0], node_centers["Node C"][1] + 0.07, color="#1d4ed8", lw=2.0, style="<->")

    # Notes
    ax.text(0.08, 0.355, "Local peer-to-peer state exchange (no central hub)", fontsize=10, color="#0f766e")
    ax.text(0.08, 0.09, "All control decisions are made at the edge", fontsize=10, color="#9a3412")

    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
