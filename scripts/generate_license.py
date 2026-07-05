"""CLI tool for generating RSA keypairs and signed licenses."""

import argparse
import base64
import json
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)


def generate_keypair(output_dir: Path) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    priv_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )
    pub_pem = public_key.public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    )

    (output_dir / "license_private_key.pem").write_bytes(priv_pem)
    (output_dir / "license_public_key.pem").write_bytes(pub_pem)
    print(f"Keypair generated in {output_dir}")


def sign_license(
    store_name: str,
    max_devices: int,
    expires: str,
    private_key_path: Path,
    output_path: Path,
) -> None:
    priv_pem = private_key_path.read_bytes()
    private_key = load_pem_private_key(priv_pem, password=None)

    payload = {
        "store_name": store_name,
        "max_devices": max_devices,
        "issued_at": datetime.now(UTC).isoformat(),
        "expires_at": expires,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )

    signature = private_key.sign(
        payload_bytes,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    payload["signature"] = base64.b64encode(signature).decode("ascii")

    output_path.write_text(json.dumps(payload, indent=2))
    print(f"License written to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="License generator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen = subparsers.add_parser("generate-keypair")
    gen.add_argument("--output-dir", type=Path, default=Path("."))

    sign = subparsers.add_parser("sign")
    sign.add_argument("--store-name", required=True)
    sign.add_argument("--max-devices", type=int, default=1)
    sign.add_argument("--expires", required=True, help="ISO date like 2027-12-31")
    sign.add_argument("--private-key", type=Path, required=True)
    sign.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()

    if args.command == "generate-keypair":
        generate_keypair(args.output_dir)
    elif args.command == "sign":
        # Format the date properly for ISO format if it's just a YYYY-MM-DD
        if "T" not in args.expires:
            args.expires += "T23:59:59Z"
        sign_license(
            args.store_name,
            args.max_devices,
            args.expires,
            args.private_key,
            args.output,
        )


if __name__ == "__main__":
    main()
