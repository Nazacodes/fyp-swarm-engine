# Communication Layer

This project uses:
- UDP broadcast discovery (`discovery_port`)
- TCP message transport (`peer_port`)
- Ack/retry with bounded attempts
- Heartbeat freshness for liveness
- Replay protection via `(sender_id, seq, timestamp)`

Primary implementation lives in `src/messaging.py` (`LanMessenger`).

Fault-injection helper:
- `experiments/fault_injection.py`
