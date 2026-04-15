#!/usr/bin/env python
"""Build statistics, tables, and plots from experiment outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "reports" / "tables"
FIGURES = ROOT / "reports" / "figures"


def _read_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_scalability_plot(data: Dict) -> None:
    xs: List[int] = []
    ys: List[float] = []
    for item in data.get("results", []):
        xs.append(item["node_count"])
        ys.append(item["summary"]["p95_latency_ms"])
    plt.figure(figsize=(8, 5))
    plt.plot(xs, ys, marker="o")
    plt.title("Scalability: p95 latency vs nodes")
    plt.xlabel("Node count")
    plt.ylabel("p95 latency (ms)")
    plt.grid(True, alpha=0.3)
    FIGURES.mkdir(parents=True, exist_ok=True)
    plt.savefig(FIGURES / "scalability_p95_latency.png", dpi=160, bbox_inches="tight")
    plt.close()


def build_aco_vs_static_plot(data: Dict) -> None:
    history = data.get("history", [])
    rounds = [h["round"] for h in history]
    aco = [h["aco_latency"] for h in history]
    static = [h["static_latency"] for h in history]
    plt.figure(figsize=(9, 5))
    plt.plot(rounds, aco, label="ACO latency")
    plt.plot(rounds, static, label="Static latency")
    plt.title("ACO vs Static Routing Latency")
    plt.xlabel("Round")
    plt.ylabel("Path cost (proxy latency)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    FIGURES.mkdir(parents=True, exist_ok=True)
    plt.savefig(FIGURES / "aco_vs_static_latency.png", dpi=160, bbox_inches="tight")
    plt.close()


def write_summary_table(central: Dict, aco: Dict, scale: Dict) -> None:
    lines = [
        "metric,value",
        f"centralized_mean_error,{central['summary']['mean_error']:.5f}",
        f"centralized_p95_error,{central['summary']['p95_error']:.5f}",
        f"aco_mean_latency,{aco['summary']['aco_mean_latency']:.5f}",
        f"static_mean_latency,{aco['summary']['static_mean_latency']:.5f}",
        f"aco_delivery_rate,{aco['summary']['aco_delivery_rate']:.5f}",
        f"static_delivery_rate,{aco['summary']['static_delivery_rate']:.5f}",
    ]
    TABLES.mkdir(parents=True, exist_ok=True)
    (TABLES / "summary.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # also include one compact scalability row set
    rows = ["node_count,p95_latency_ms,mean_error,mean_messages,mean_cpu_pct,mean_mem_mb"]
    for item in scale.get("results", []):
        s = item["summary"]
        rows.append(
            f"{item['node_count']},{s['p95_latency_ms']:.5f},{s['mean_error']:.5f},"
            f"{s['mean_messages']:.5f},{s['mean_cpu_pct']:.5f},{s['mean_mem_mb']:.5f}"
        )
    (TABLES / "scalability_summary.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    central = _read_json(TABLES / "centralized_baseline.json")
    aco = _read_json(TABLES / "aco_routing_experiment.json")
    scale = _read_json(TABLES / "scalability.json")
    build_scalability_plot(scale)
    build_aco_vs_static_plot(aco)
    write_summary_table(central, aco, scale)
    print("Report artifacts generated in reports/figures and reports/tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
