"""Local PIN hashing — PBKDF2-SHA256 via the standard library.

The PIN is only ever stored as a salted hash (PIN_HASH in .env), never in
plaintext. Format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>.
"""

import hashlib
import hmac
import secrets

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 200_000


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored_hash: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored_hash.split("$")
        if algo != _ALGO:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False
