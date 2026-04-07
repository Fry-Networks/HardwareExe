#!/usr/bin/env python3
"""Manage encrypted Honeygain SDK credentials."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError as exc:  # pragma: no cover
    raise SystemExit("cryptography package is required to manage Honeygain secrets") from exc


SALT = b"honeygain_config_salt_v1"
PASSWORD = "honeygain_config_encryption_key_v1"


def _derive_key() -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(PASSWORD.encode()))


def encrypt_honeygain_secret(secret: dict) -> dict:
    """Encrypt the Honeygain secret dictionary."""
    key = _derive_key()
    fernet = Fernet(key)
    payload = json.dumps(secret).encode("utf-8")
    encrypted = fernet.encrypt(payload)
    return {"data": encrypted.decode("utf-8"), "version": "1.0"}


def decrypt_honeygain_secret(blob: dict) -> dict:
    """Decrypt an existing honeygain.enc blob."""
    key = _derive_key()
    payload = blob.get("data")
    if not isinstance(payload, str):
        raise ValueError("Secret payload missing 'data' field")
    fernet = Fernet(key)
    decrypted = fernet.decrypt(payload.encode("utf-8"))
    return json.loads(decrypted.decode("utf-8"))


def create_honeygain_secret(api_key: str, output: str | None) -> Path:
    """Create an encrypted honeygain.enc file."""
    if not api_key or not isinstance(api_key, str):
        raise ValueError("api_key must be a non-empty string")
    target = Path(output or "honeygain.enc").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = encrypt_honeygain_secret(
        {"api_key": api_key.strip(), "created_by": "installer", "config_version": "1.0"}
    )
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage encrypted Honeygain SDK config")
    subparsers = parser.add_subparsers(dest="command")

    create_parser = subparsers.add_parser("create", help="Create encrypted honeygain.enc")
    create_parser.add_argument("api_key", help="Honeygain API key issued to FryNetworks")
    create_parser.add_argument("--output", "-o", help="Output file path (default: honeygain.enc)")

    read_parser = subparsers.add_parser("read", help="Decrypt honeygain.enc for verification")
    read_parser.add_argument("secret_file", help="Path to honeygain.enc")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    if args.command == "create":
        target = create_honeygain_secret(args.api_key, args.output)
        print(f"✅ Created Honeygain secret at {target}")
    elif args.command == "read":
        path = Path(args.secret_file).resolve()
        if not path.exists():
            raise SystemExit(f"Secret file not found: {path}")
        blob = json.loads(path.read_text(encoding="utf-8"))
        data = decrypt_honeygain_secret(blob)
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
