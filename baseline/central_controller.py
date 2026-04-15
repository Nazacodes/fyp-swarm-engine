#!/usr/bin/env python
"""Centralized baseline simulation for comparison with decentralized ACO."""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from pathlib import Path
from typing import Dict, List


def run_baseline(nodes: int, rounds: int, target_temp: float, seed: int) -> Dict:
    random.seed(seed)
    temps = [random.uniform(10.0, 34.0) for _ in range(nodes)]
    records: List[Dict] = []
    for idx in range(rounds):
        start = time.perf_counter()
        avg = sum(temps) / len(temps)
        if avg < target_temp - 0.2:
            delta = 0.18
        elif avg > target_temp + 0.2:
            delta = -0.18
        else:
            delta = 0.0
        temps = [t + delta + random.uniform(-0.04, 0.04) for t in temps]
        lat_ms = (time.perf_counter() - start) * 1000.0
        records.append(
            {
                "round": idx,
                "mode": "centralized",
                "avg_temp": sum(temps) / len(temps),
                "error": abs((sum(temps) / len(temps)) - target_temp),
                "latency_ms": lat_ms,
                "message_count": nodes,
            }
        )
    errs = [r["error"] for r in records]
    return {
        "mode": "centralized",
        "nodes": nodes,
        "rounds": rounds,
        "target_temp": target_temp,
        "records": records,
        "summary": {
            "mean_error": statistics.mean(errs),
            "p95_error": sorted(errs)[max(0, int(len(errs) * 0.95) - 1)],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Centralized baseline simulation")
    parser.add_argument("--nodes", type=int, default=20)
    parser.add_argument("--rounds", type=int, default=120)
    parser.add_argument("--target-temp", type=float, default=22.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="reports/tables/centralized_baseline.json")
    args = parser.parse_args()
    result = run_baseline(args.nodes, args.rounds, args.target_temp, args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote baseline results to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
