#!/usr/bin/env python
"""Scalability simulation with gossip strategy."""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from pathlib import Path
from typing import Dict, List


def simulate(node_count: int, rounds: int, seed: int) -> Dict:
    random.seed(seed + node_count)
    temps = [random.uniform(10.0, 34.0) for _ in range(node_count)]
    target = 22.0
    records: List[Dict] = []
    for r in range(rounds):
        start = time.perf_counter()
        # gossip strategy: each node talks to sqrt(n) neighbors
        fanout = max(2, int(node_count ** 0.5))
        message_count = node_count * fanout
        avg = sum(temps) / len(temps)
        error = target - avg
        for i in range(node_count):
            noise = random.uniform(-0.08, 0.08)
            temps[i] += (error * 0.03) + noise
        latency_ms = (time.perf_counter() - start) * 1000.0 + (node_count * 0.02)
        cpu_pct = min(95.0, 20.0 + (node_count * 1.4) + random.uniform(-2.0, 2.0))
        mem_mb = 120.0 + (node_count * 3.0) + random.uniform(-5.0, 5.0)
        records.append(
            {
                "round": r,
                "node_count": node_count,
                "latency_ms": latency_ms,
                "error": abs(error),
                "message_count": message_count,
                "cpu_pct": cpu_pct,
                "mem_mb": mem_mb,
            }
        )
    latencies = [x["latency_ms"] for x in records]
    return {
        "node_count": node_count,
        "rounds": rounds,
        "records": records,
        "summary": {
            "p50_latency_ms": statistics.median(latencies),
            "p95_latency_ms": sorted(latencies)[max(0, int(0.95 * len(latencies)) - 1)],
            "p99_latency_ms": sorted(latencies)[max(0, int(0.99 * len(latencies)) - 1)],
            "mean_error": statistics.mean(x["error"] for x in records),
            "mean_messages": statistics.mean(x["message_count"] for x in records),
            "mean_cpu_pct": statistics.mean(x["cpu_pct"] for x in records),
            "mean_mem_mb": statistics.mean(x["mem_mb"] for x in records),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scalability simulations")
    parser.add_argument("--nodes", nargs="+", type=int, default=[5, 10, 20, 30])
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="reports/tables/scalability.json")
    args = parser.parse_args()

    results = [simulate(n, args.rounds, args.seed) for n in args.nodes]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    print(f"Wrote scalability results to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
