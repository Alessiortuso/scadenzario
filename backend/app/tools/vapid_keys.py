"""Genera una coppia di chiavi VAPID per il Web Push.

Uso:
    python -m app.tools.vapid_keys

Copiare l'output in `.env` (VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY).
Le chiavi vanno generate una sola volta: cambiandole, tutte le iscrizioni
esistenti dei browser smettono di funzionare e vanno rifatte.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate() -> tuple[str, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_raw = private_key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    private_raw = private_key.private_numbers().private_value.to_bytes(32, "big")
    return _b64(public_raw), _b64(private_raw)


if __name__ == "__main__":
    public, private = generate()
    print("VAPID_PUBLIC_KEY=" + public)
    print("VAPID_PRIVATE_KEY=" + private)
