# Protocol-Agnostic Runtime Notes

This swarm runtime now uses a protocol-agnostic control plane:

- Swarm logic (`src/node.py`, `src/aco.py`) is independent of transport details.
- Transport adapter selection happens in `src/messaging.py`.
- `protocol_mode` describes logical protocol identity for nodes:
  - `ip`
  - `rabbitmq`
  - `zigbee-gateway`
  - `thread-gateway`
  - `ble-gateway`

## How it works

1. Nodes publish the same message schema regardless of protocol.
2. Gateway protocol modes (`zigbee/thread/ble`) are mapped to a transport adapter
   while retaining logical protocol identity in payloads.
3. The monitor and leader council operate on normalized topics, not protocol-specific APIs.

## Example

Set a node to simulate Zigbee-device-via-gateway:

```powershell
set PROTOCOL_MODE=zigbee-gateway
set MESSAGING_MODE=rabbitmq
python src\node.py --config config_node1.json
```

This keeps swarm behavior consistent while allowing mixed-protocol deployments.
