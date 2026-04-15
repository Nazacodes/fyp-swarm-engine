#!/usr/bin/env python
"""Security primitives for auth, encryption, and replay checks."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Set, Tuple

from cryptography.fernet import Fernet, InvalidToken


def _stable_json(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


class MessageSecurity:
    """Provides signing/encryption and replay protection."""

    def __init__(self, node_id: str, psk: str, clock_skew_seconds: float = 15.0):
        self.node_id = node_id
        self.psk = psk.encode("utf-8")
        self.clock_skew_seconds = clock_skew_seconds
        self._seen: Set[Tuple[str, int]] = set()
        key = base64.urlsafe_b64encode(hashlib.sha256(self.psk).digest())
        self._fernet = Fernet(key)

    def sign(self, envelope: Dict[str, Any]) -> str:
        payload = {k: v for k, v in envelope.items() if k != "signature"}
        digest = hmac.new(self.psk, _stable_json(payload), hashlib.sha256).hexdigest()
        return digest

    def verify(self, envelope: Dict[str, Any]) -> bool:
        signature = envelope.get("signature")
        if not signature:
            return False
        expected = self.sign(envelope)
        return hmac.compare_digest(signature, expected)

    def encrypt_payload(self, payload: Dict[str, Any]) -> str:
        return self._fernet.encrypt(_stable_json(payload)).decode("utf-8")

    def decrypt_payload(self, token: str) -> Dict[str, Any]:
        raw = self._fernet.decrypt(token.encode("utf-8"))
        loaded = json.loads(raw.decode("utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("Decrypted payload must be object.")
        return loaded

    def validate_freshness_and_replay(self, sender_id: str, seq: int, timestamp: float) -> bool:
        now = time.time()
        if abs(now - timestamp) > self.clock_skew_seconds:
            return False
        key = (sender_id, seq)
        if key in self._seen:
            return False
        self._seen.add(key)
        if len(self._seen) > 10000:
            self._seen = set(list(self._seen)[-5000:])
        return True

    def safe_decrypt(self, token: str) -> Dict[str, Any]:
        try:
            return self.decrypt_payload(token)
        except InvalidToken as exc:
            raise ValueError("Invalid encrypted payload") from exc
