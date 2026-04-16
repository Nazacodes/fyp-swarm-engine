#!/usr/bin/env python
"""Migrate root-level config*.json files into nodes/configs/."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "nodes" / "configs"


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    moved = 0
    skipped = 0
    patterns = ["config_node*.json", "config_pi*.json"]
    for pattern in patterns:
        for src in sorted(ROOT.glob(pattern)):
            dst = TARGET / src.name
            if dst.exists():
                skipped += 1
                continue
            shutil.move(str(src), str(dst))
            moved += 1
    print(f"Migrated configs: moved={moved}, skipped_existing={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
