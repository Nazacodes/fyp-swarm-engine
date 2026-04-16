# FYP Swarm Engine

Distributed smart-device coordination with ACO, leader council sync, RabbitMQ messaging, and a web dashboard.

## Cleaned Repo Layout

```
fyp-swarm-engine/
├── src/
│   ├── node.py                  # Swarm node runtime
│   ├── web_monitor.py           # Dashboard/API
│   ├── messaging.py             # LAN + RabbitMQ transport adapters
│   ├── protocol_agnostic.py     # Protocol-agnostic message model/contracts
│   ├── templates/               # overview/charts/node-map pages
│   └── static/                  # UI styling
├── scripts/
│   ├── run_quickstart.bat       # Main launcher (recommended)
│   ├── run_quickstart.ps1       # Main launcher (PowerShell)
│   ├── supervisor.py            # Batching + node health supervision
│   ├── swarm_beacon.py          # Host discovery beacon (UDP)
│   ├── join_swarm.py            # Edge auto-discovery join helper
│   ├── gateway_client.py        # HTTP gateway join simulator
│   ├── bluetooth_adapter_rmq.py # BLE-style join over RabbitMQ
│   └── ble_adapter.py           # Real BLE adapter (bleak)
├── nodes/
│   ├── README.md
│   └── configs/                 # Preferred home for config_node*.json
├── algorithms/ baseline/ experiments/ analysis/
└── docs/
```

## Prerequisites

- Python 3.10+
- RabbitMQ running locally (`localhost:5672`) for standard runs

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Primary Way To Run

Use one launcher only:

```bat
scripts\run_quickstart.bat 20 5000 5 4
```

Arguments:
- `20` = node count
- `5000` = monitor port
- `5` = batch size
- `4` = groups (enables multiple leaders)

Open:
- `http://localhost:5000` (overview)
- `http://localhost:5000/charts`
- `http://localhost:5000/node-map`

## Node Config Location

Canonical config path:
1. `nodes/configs/config_nodeN.json`

One-time migration (moves root configs into `nodes/configs/`):

```bash
python scripts/migrate_node_configs.py
```

Regenerate configs directly into `nodes/configs/`:

```bash
python generate_configs.py
python generate_10_configs.py
```

## Protocol-Agnostic Join Paths

- Native node runtime: `src/node.py`
- HTTP gateway join: `scripts/gateway_client.py`
- Auto-discovery edge join (Pi-friendly): `scripts/join_swarm.py`
- BLE over RabbitMQ: `scripts/bluetooth_adapter_rmq.py`
- Real BLE hardware adapter: `scripts/ble_adapter.py`

See:
- `docs/protocol_agnostic.md`
- `docs/bluetooth_rabbitmq_adapter.md`
- `docs/ble_real_adapter.md`
- `docs/RUN_SCRIPTS.md`

## Raspberry Pi Auto-Join

Host machine (already running quickstart/supervisor) automatically advertises swarm
connection details on UDP discovery.

On Raspberry Pi:

```bash
python3 scripts/join_swarm.py --node-id pi-node1 --group-id zone_2
```

This discovers the host RabbitMQ endpoint and starts `src/node.py` with the
discovered settings.

## Notes

- Dashboard supports target updates from Overview page.
- Leader council sync propagates target changes across groups.
- Node map shows member→leader and leader-council links.
- Use `scripts/run_quickstart.*` + `scripts/supervisor.py` as the only runtime launcher path.
