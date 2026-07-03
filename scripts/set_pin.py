"""Set (or reset) the owner PIN — writes PIN_HASH to the project .env.

Usage (from the project root, venv active):

    python scripts/set_pin.py 1234

The PIN itself is never stored — only a salted PBKDF2 hash.
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.security import hash_pin  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("Usage: python scripts/set_pin.py <PIN>")
        return 1

    pin_hash = hash_pin(sys.argv[1].strip())
    env_path = PROJECT_ROOT / ".env"
    content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

    if re.search(r"^PIN_HASH=.*$", content, flags=re.MULTILINE):
        content = re.sub(
            r"^PIN_HASH=.*$", f"PIN_HASH={pin_hash}", content, flags=re.MULTILINE
        )
    else:
        content = (
            content.rstrip("\n") + ("\n" if content else "") + f"PIN_HASH={pin_hash}\n"
        )

    env_path.write_text(content, encoding="utf-8")
    print(f"PIN hash written to {env_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
