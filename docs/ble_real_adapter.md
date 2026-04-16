# Real BLE Adapter (Bleak)

This adapter connects to actual nearby BLE peripherals and feeds them into the swarm over RabbitMQ.

- Script: `scripts/ble_adapter.py`
- BLE stack: `bleak`
- Swarm transport: RabbitMQ
- Protocol identity: `ble-gateway`

## Install

```bash
python -m pip install bleak
```

## Run

```bash
python scripts/ble_adapter.py \
  --rabbit-host localhost \
  --rabbit-user guest \
  --rabbit-password guest \
  --group-id zone_1 \
  --scan-seconds 6 \
  --poll-seconds 2
```

## Notes

- Adapter scans BLE devices and attempts to read temperature from common UUIDs:
  - `0x2A1C` (Health Thermometer)
  - `0x2A6E` (Environmental Sensing)
- Devices without readable temperature characteristics will still be discovered, but telemetry temperature may remain `None`.
- You can extend `TEMP_CHAR_UUIDS` in the script for your device-specific characteristics.

