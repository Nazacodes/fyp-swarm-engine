#!/usr/bin/env python
"""Fault injection helper for packet delay/loss/dropout simulation."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate fault schedule for experiments")
    parser.add_argument("--rounds", type=int, default=120)
    parser.add_argument("--loss-rate", type=float, default=0.05)
    parser.add_argument("--max-delay-ms", type=int, default=300)
    parser.add_argument("--dropout-every", type=int, default=25)
    parser.add_argument("--out", type=str, default="experiments/scenarios/fault_schedule.json")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    random.seed(args.seed)
    schedule = []
    for r in range(args.rounds):
        schedule.append(
            {
                "round": r,
                "drop_packet": random.random() < args.loss_rate,
                "delay_ms": random.randint(0, args.max_delay_ms),
                "drop_node": (r > 0 and r % args.dropout_every == 0),
            }
        )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"faults": schedule}, indent=2), encoding="utf-8")
    print(f"Wrote fault schedule to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
