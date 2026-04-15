# Security Test Checklist

- [ ] Node with wrong PSK fails to publish valid signed messages.
- [ ] Node not in allow-list is ignored by recipients.
- [ ] Tampered message body fails signature verification.
- [ ] Replay of same `(sender_id, seq)` is rejected.
- [ ] Message older than clock skew threshold is rejected.
- [ ] Payload encrypted in transit (`payload_enc`) when encryption is enabled.
- [ ] Target update endpoint protected by auth policy (if deployed externally).
