#!/usr/bin/env python
"""ACO routing experiment with impaired links."""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.aco import ACORouter


def _rand_cost() -> float:
    return random.uniform(0.8, 5.0)


def run_aco_vs_static(nodes: int, rounds: int, seed: int) -> Dict:
    random.seed(seed)
    router = ACORouter()
    edges = [(f"n{i}", f"n{i+1}") for i in range(nodes - 1)]
    reverse = [(b, a) for a, b in edges]
    graph_edges = edges + reverse

    aco_latencies: List[float] = []
    static_latencies: List[float] = []
    aco_delivery = 0
    static_delivery = 0
    history: List[Dict] = []

    for r in range(rounds):
        link_cost: Dict[Tuple[str, str], float] = {edge: _rand_cost() for edge in graph_edges}
        # Inject impairment spike intermittently
        if r % 10 == 0:
            edge = random.choice(graph_edges)
            link_cost[edge] *= 3.0

        # static route n0->n1->...->n{N-1}
        static_path = [(f"n{i}", f"n{i+1}") for i in range(nodes - 1)]
        static_cost = sum(link_cost.get(edge, 10.0) for edge in static_path)
        static_ok = static_cost < nodes * 4.5
        static_delivery += 1 if static_ok else 0
        static_latencies.append(static_cost)

        # ACO route (myopic next-hop from chain + optional skip)
        aco_path: List[Tuple[str, str]] = []
        current = "n0"
        while current != f"n{nodes-1}":
            idx = int(current[1:])
            candidates = []
            if idx + 1 < nodes:
                candidates.append(f"n{idx+1}")
            if idx + 2 < nodes:
                candidates.append(f"n{idx+2}")
            nxt = router.choose_next_hop(current, candidates, link_cost)
            if nxt == current:
                break
            edge = (current, nxt)
            aco_path.append(edge)
            current = nxt
            if len(aco_path) > nodes + 2:
                break
        aco_cost = sum(link_cost.get(edge, 10.0) for edge in aco_path) if aco_path else 999.0
        aco_ok = current == f"n{nodes-1}" and aco_cost < nodes * 4.5
        aco_delivery += 1 if aco_ok else 0
        aco_latencies.append(aco_cost)
        router.reinforce_path(aco_path, aco_cost if aco_cost > 0 else 1.0)

        history.append(
            {
                "round": r,
                "aco_latency": aco_cost,
                "static_latency": static_cost,
                "aco_delivered": aco_ok,
                "static_delivered": static_ok,
            }
        )

    return {
        "meta": {"nodes": nodes, "rounds": rounds, "seed": seed},
        "history": history,
        "summary": {
            "aco_mean_latency": statistics.mean(aco_latencies),
            "static_mean_latency": statistics.mean(static_latencies),
            "aco_p95_latency": sorted(aco_latencies)[max(0, int(0.95 * len(aco_latencies)) - 1)],
            "static_p95_latency": sorted(static_latencies)[max(0, int(0.95 * len(static_latencies)) - 1)],
            "aco_delivery_rate": aco_delivery / rounds,
            "static_delivery_rate": static_delivery / rounds,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ACO routing experiment")
    parser.add_argument("--nodes", type=int, default=20)
    parser.add_argument("--rounds", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="reports/tables/aco_routing_experiment.json")
    args = parser.parse_args()
    result = run_aco_vs_static(nodes=args.nodes, rounds=args.rounds, seed=args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote ACO routing results to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
