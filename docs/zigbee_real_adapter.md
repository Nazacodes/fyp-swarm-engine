# Real Zigbee Adapter (Zigbee2MQTT)

This project now includes a practical adapter for physical Zigbee devices:

- Script: `scripts/zigbee_adapter.py`
- Bridge: Zigbee2MQTT MQTT topics -> swarm gateway API
- Result: real Zigbee devices join swarm as protocol-agnostic logical nodes

## Prerequisites

1. Zigbee coordinator + Zigbee2MQTT running.
2. MQTT broker reachable (default `localhost:1883`).
3. Swarm monitor running on `localhost:5000`.

Install dependency:

```bash
python -m pip install paho-mqtt
```

## Run

```bash
python scripts/zigbee_adapter.py \
  --swarm-host localhost --swarm-port 5000 \
  --mqtt-host localhost --mqtt-port 1883 \
  --mqtt-topic-prefix zigbee2mqtt \
  --group-id zone_1 \
  --protocol-mode zigbee-gateway
```

## What it does

1. Subscribes to `zigbee2mqtt/<friendly_name>/...` topics.
2. Reads sensor payloads (e.g. `temperature`).
3. Joins each Zigbee device to swarm through `/api/gateway/join`.
4. Sends heartbeat + telemetry via gateway API.
5. Pulls global target from swarm and pushes `target_temp` to Zigbee2MQTT set topics.

## Notes

- Device command schemas vary by converter/device in Zigbee2MQTT.
- The script sends a generic `{ "target_temp": <value> }` set payload.
- If your device expects different keys, adapt `_push_target_to_devices()` accordingly.
