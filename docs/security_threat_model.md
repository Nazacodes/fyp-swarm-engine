# Security Threat Model

## Scope
- Local LAN swarm node communication.
- Node join/authentication and message integrity.
- Telemetry confidentiality in transit.

## Trust Assumptions
- Nodes share a pre-shared key (PSK) out-of-band.
- LAN is potentially hostile (insider sniffing/spoofing possible).
- Node clocks can drift by a small bounded amount.

## Threats, Mitigations, Residual Risk

| Threat | Mitigation | Residual Risk |
|---|---|---|
| Unauthorized node joins swarm | Node allow-list and HMAC signatures with PSK | Compromise of PSK compromises trust boundary |
| Message tampering | HMAC integrity check over message envelope | No non-repudiation; shared key only |
| Passive LAN sniffing | Encrypted payload (Fernet/AES under PSK-derived key) | Metadata (topic/timing/sender) still observable |
| Replay attacks | Sender sequence cache + timestamp freshness window | Very large cache churn may evict old entries |
| Stale node takeover | Heartbeat + staleness timeout + peer table aging | False positives under severe network jitter |

## Planned Hardening (Future)
- Per-node certificates and mTLS.
- Key rotation and revocation workflow.
- Audit logs and anomaly detection for suspicious join patterns.
