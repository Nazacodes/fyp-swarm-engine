# Bluetooth Adapter (RabbitMQ Native)

Use this when you want protocol-agnostic demonstration without adding MQTT/Zigbee stack.

- Script: `scripts/bluetooth_adapter_rmq.py`
- Transport: existing RabbitMQ queue
- Protocol identity: `ble-gateway`

## Run

```bash
python scripts/bluetooth_adapter_rmq.py \
  --rabbit-host localhost \
  --rabbit-user guest \
  --rabbit-password guest \
  --group-id zone_2 \
  --devices 3 \
  --start-temp 19.5
```

## What it does

1. Creates N logical BLE devices (default 2).
2. Publishes heartbeat and telemetry on standard swarm topics:
   - `swarm.temperature.heartbeat.<node_id>`
   - `swarm.temperature.telemetry.<node_id>`
3. Subscribes to `swarm.temperature.cmd.target.set`.
4. Moves BLE temperatures toward the global target.

## Why this helps

- Works with your current RabbitMQ-only setup.
- Demonstrates protocol-agnostic joining path (BLE via gateway identity) immediately.
- No extra broker/hardware required for the demo.
