#!/usr/bin/env python3
"""Manage encrypted Bright SDK credentials (Windows only)."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError as exc:  # pragma: no cover
    raise SystemExit("cryptography package is required to manage Bright secrets") from exc

SALT = b"bright_config_salt_v1"
PASSWORD = "bright_config_encryption_key_v1"


def _derive_key() -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(PASSWORD.encode()))


def encrypt_bright_secret(secret: dict) -> dict:
    key = _derive_key()
    fernet = Fernet(key)
    payload = json.dumps(secret).encode("utf-8")
    encrypted = fernet.encrypt(payload)
    return {"data": encrypted.decode("utf-8"), "version": "1.0"}


def decrypt_bright_secret(blob: dict) -> dict:
    key = _derive_key()
    payload = blob.get("data")
    if not isinstance(payload, str):
        raise ValueError("Secret payload missing 'data' field")
    fernet = Fernet(key)
    decrypted = fernet.decrypt(payload.encode("utf-8"))
    return json.loads(decrypted.decode("utf-8"))


def create_bright_secret(app_id: str, output: str | None) -> Path:
    if not app_id or not isinstance(app_id, str):
        raise ValueError("app_id must be a non-empty string")
    target = Path(output or "bright.enc").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = encrypt_bright_secret(
        {"app_id": app_id.strip(), "created_by": "installer", "config_version": "1.0"}
    )
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage encrypted Bright SDK config")
    subparsers = parser.add_subparsers(dest="command")

    create_parser = subparsers.add_parser("create", help="Create encrypted bright.enc")
    create_parser.add_argument("app_id", help="Bright app id (provided by Bright SDK)")
    create_parser.add_argument("--output", "-o", help="Output file path (default: bright.enc)")

    read_parser = subparsers.add_parser("read", help="Decrypt bright.enc for verification")
    read_parser.add_argument("secret_file", help="Path to bright.enc")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    if args.command == "create":
        target = create_bright_secret(args.app_id, args.output)
        print(f"✅ Created Bright secret at {target}")
    elif args.command == "read":
        path = Path(args.secret_file).resolve()
        if not path.exists():
            raise SystemExit(f"Secret file not found: {path}")
        blob = json.loads(path.read_text(encoding="utf-8"))
        data = decrypt_bright_secret(blob)
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
