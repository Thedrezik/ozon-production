"""Generate VAPID configuration into a private, untracked file, without printing keys."""

import base64
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def generate(path: Path):
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    private = key.private_numbers().private_value.to_bytes(32, "big")
    def encode(value):
        return base64.urlsafe_b64encode(value).decode().rstrip("=")
    with path.open("x", encoding="utf-8") as output:
        output.write(f"VAPID_PUBLIC_KEY={encode(public)}\nVAPID_PRIVATE_KEY={encode(private)}\n"
                     "VAPID_SUBJECT=mailto:admin@example.com\n")
    path.chmod(0o600)


if __name__ == "__main__":
    generate(Path(".env.vapid"))
