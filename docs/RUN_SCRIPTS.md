# Run Scripts Index

This project keeps a small set of operational scripts in `scripts/`.

## Core launch scripts

- `scripts/run_quickstart.bat`  
  Main launcher on Windows CMD. Starts supervisor flow.

- `scripts/run_quickstart.ps1`  
  Main launcher on PowerShell (if execution policy allows).

- `scripts/supervisor.py`  
  Starts monitor + nodes in batches and restarts stale/dead nodes.

## Discovery / edge-join scripts

- `scripts/swarm_beacon.py`  
  Broadcasts swarm host info over UDP for LAN discovery.

- `scripts/join_swarm.py`  
  Edge-device auto-discovery join helper (Pi-friendly).

## Protocol-agnostic / adapter scripts

- `scripts/gateway_client.py`  
  Generic gateway join simulator over HTTP API.

- `scripts/bluetooth_adapter_rmq.py`  
  BLE-style adapter using RabbitMQ transport (no BLE hardware required).

- `scripts/ble_adapter.py`  
  Real BLE adapter using `bleak` and RabbitMQ.


## Repo maintenance

- `scripts/migrate_node_configs.py`  
  Moves `config_node*.json`/`config_pi*.json` into `nodes/configs/`.

## Typical run commands

```bat
scripts\run_quickstart.bat 20 5000 5 4
```

```bash
python scripts/join_swarm.py --node-id pi-node1 --group-id zone_2
```
