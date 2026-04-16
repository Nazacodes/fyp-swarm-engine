# FYP Swarm Engine

This project runs a decentralized smart-device swarm using:
- ACO-based local control
- leader + leader-council coordination
- RabbitMQ messaging
- a web dashboard for monitoring and control

The goal is to test swarm behavior at scale (for example 20+ nodes) with clear, repeatable experiments.

## What Is Working (Current Baseline)

- Main runtime: `scripts/run_quickstart.bat` + `scripts/supervisor.py`
- Transport: RabbitMQ
- Monitor UI/API: `src/web_monitor.py`
- Protocol-agnostic join paths:
  - native node runtime (`src/node.py`)
  - HTTP gateway join (`scripts/gateway_client.py`)
  - LAN auto-discovery join (`scripts/join_swarm.py`)
  - BLE-style RabbitMQ adapter (`scripts/bluetooth_adapter_rmq.py`)
  - real BLE adapter (`scripts/ble_adapter.py`)

## Project Layout (Important Parts)

```text
fyp-swarm-engine/
├── src/                         # Core runtime (node, messaging, monitor, UI)
├── scripts/                     # Launchers, adapters, supervisor, discovery tools
├── nodes/configs/               # Node config files (config_node*.json)
├── algorithms/                  # ACO experiment modules
├── baseline/                    # Centralized baseline comparison
├── experiments/                 # Experiment runners/scenarios
├── analysis/                    # Plots + report generation
└── docs/                        # Operational and architecture docs
```

## Prerequisites

- Python 3.10+
- RabbitMQ running on `localhost:5672` (default setup)

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Quick Start (Recommended)

Run from project root:

```bat
scripts\run_quickstart.bat 20 5000 5 4
```

Meaning of arguments:
- `20` -> number of nodes
- `5000` -> monitor port
- `5` -> batch size for node startup
- `4` -> number of groups (multi-leader setup)

Then open:
- `http://localhost:5000` (overview)
- `http://localhost:5000/charts`
- `http://localhost:5000/node-map`

## Node Config Files

Use this folder as the source of truth:
- `nodes/configs/config_nodeN.json`

If old config files still exist in root, migrate once:

```bash
python scripts/migrate_node_configs.py
```

Regenerate config files directly into `nodes/configs/`:

```bash
python generate_configs.py
python generate_10_configs.py
```

## Raspberry Pi / Edge Join

If your host is already running quickstart/supervisor, it broadcasts swarm connection info over UDP.

On Raspberry Pi (or another edge device), run:

```bash
python3 scripts/join_swarm.py --node-id pi-node1 --group-id zone_2
```

This auto-discovers the host and starts `src/node.py` with discovered connection settings.

## Useful Docs

- `docs/protocol_agnostic.md`
- `docs/bluetooth_rabbitmq_adapter.md`
- `docs/ble_real_adapter.md`
- `docs/RUN_SCRIPTS.md`

## Notes

- You can change target temperature from the Overview page.
- Leaders synchronize target changes across groups using leader-council logic.
- Node map shows member-to-leader and leader-to-leader links.
- For reliable runs, use `scripts/run_quickstart.*` and `scripts/supervisor.py` as the standard launcher path.
