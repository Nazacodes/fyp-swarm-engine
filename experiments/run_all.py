#!/usr/bin/env python
"""One-command reproducible experiment runner."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(cmd: list[str]) -> None:
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all experiments and build reports")
    parser.add_argument("--manifest", default="experiments/scenarios/manifest.json")
    args = parser.parse_args()
    manifest_path = ROOT / args.manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    seed = int(manifest.get("seed", 42))
    rounds = int(manifest.get("rounds", 120))
    started = int(time.time())
    out_root = ROOT / "reports" / "tables" / f"run_{started}"
    out_root.mkdir(parents=True, exist_ok=True)

    run([PY, "experiments/fault_injection.py", "--rounds", str(rounds), "--seed", str(seed)])
    run(
        [
            PY,
            "baseline/central_controller.py",
            "--nodes",
            "20",
            "--rounds",
            str(rounds),
            "--seed",
            str(seed),
            "--out",
            "reports/tables/centralized_baseline.json",
        ]
    )
    run(
        [
            PY,
            "algorithms/aco_routing.py",
            "--nodes",
            "20",
            "--rounds",
            str(rounds * 2),
            "--seed",
            str(seed),
            "--out",
            "reports/tables/aco_routing_experiment.json",
        ]
    )
    run([PY, "experiments/scalability/run_scalability.py", "--rounds", str(rounds), "--seed", str(seed), "--out", "reports/tables/scalability.json"])
    run([PY, "analysis/build_reports.py"])

    # Save immutable copy for this run
    for file_name in ["centralized_baseline.json", "aco_routing_experiment.json", "scalability.json", "summary.csv", "scalability_summary.csv"]:
        src = ROOT / "reports" / "tables" / file_name
        if src.exists():
            (out_root / file_name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"All experiments complete. Snapshot stored in {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
