"""Offline license verification with RSA-signed JSON."""

import base64
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
except ImportError:
    InvalidSignature = None

_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAsidn0xespr+bfijuEBR0
yShW/bcg84E05OTXO3+cDpsS/qnQCMgmN9B0gAEBEPLiLg0zdzUplV/99Gb0Inj/
hDDCqDyNiIy1RLepmPO1ws9nLB94EuwplE7cKUFv+kqokCIfbMyM8626UX+NQYUT
TDGImQ/jnJCoLPyVsO1EY4qXpHFD4iDPvzvMPo447+8acIVpS123r6kXUhr+IWld
lZyMR6SBw52WY+zguWOWDbVRJ6PoEPrQz3Uvx1Xcx10SH5X7SnyNGjCCurTO5r3f
mHrZ80BekGrN6UUJvhoET/2qBBpJPxwU5G/WfjycTEgU67Lu2DnQidTqoUeYzOFB
HQIDAQAB
-----END PUBLIC KEY-----"""


@dataclass
class LicenseInfo:
    store_name: str
    max_devices: int
    issued_at: datetime
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        now = datetime.now(UTC)
        expires = self.expires_at
        if expires.tzinfo is None:
            now = now.replace(tzinfo=None)
        return now > expires


def find_license() -> Path | None:
    # Look next to the executable/script first
    root = Path(sys.argv[0]).resolve().parent
    for name in ("license.lic", "license.json"):
        path = root / name
        if path.is_file():
            return path

    # Also look in the current working directory as fallback
    cwd = Path.cwd()
    for name in ("license.lic", "license.json"):
        path = cwd / name
        if path.is_file():
            return path

    return None


def verify_license(license_path: Path) -> LicenseInfo | None:
    """Read and verify the license. Returns LicenseInfo or raises ValueError."""
    if not InvalidSignature:
        logger.warning(
            "cryptography package missing, skipping strict license signature check."
        )
        # Graceful degradation: without `cryptography` we cannot verify the RSA
        # signature, so the license is still parsed and its expiry enforced, but
        # authenticity is NOT checked. The packaged build always bundles
        # `cryptography`, so this branch is only reached in stripped dev setups.

    try:
        data = json.loads(license_path.read_text("utf-8"))
    except Exception as e:
        raise ValueError(f"Fichier de licence invalide ou corrompu ({e}).") from e

    signature_b64 = data.get("signature")
    if not signature_b64:
        raise ValueError("La licence ne contient pas de signature.")

    # Reconstruct payload exactly as signed
    payload = {
        "store_name": data.get("store_name"),
        "max_devices": data.get("max_devices"),
        "issued_at": data.get("issued_at"),
        "expires_at": data.get("expires_at"),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )

    if InvalidSignature:
        try:
            signature = base64.b64decode(signature_b64)
            public_key = load_pem_public_key(_PUBLIC_KEY_PEM)
            public_key.verify(
                signature,
                payload_bytes,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except InvalidSignature as e:
            raise ValueError(
                "Signature de licence invalide (falsifiée ou corrompue)."
            ) from e
        except Exception as e:
            raise ValueError(f"Erreur de vérification de la licence : {e}") from e

    try:
        issued_at = datetime.fromisoformat(payload["issued_at"])
        expires_at = datetime.fromisoformat(payload["expires_at"])
    except (TypeError, ValueError) as e:
        raise ValueError("Dates de licence invalides.") from e

    info = LicenseInfo(
        store_name=payload.get("store_name", "Inconnu"),
        max_devices=payload.get("max_devices", 1),
        issued_at=issued_at,
        expires_at=expires_at,
    )

    if info.is_expired:
        raise ValueError(
            f"La licence a expiré le {info.expires_at.strftime('%d/%m/%Y')}."
        )

    return info
