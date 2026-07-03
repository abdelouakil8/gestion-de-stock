"""Product image storage — strict validation, UUID-derived names, cleanup.

Security rules (non-negotiable):
- The stored filename derives ONLY from the product UUID and the DETECTED
  image format — the uploaded filename is never used, so path traversal
  through it is impossible by construction.
- Content is verified with Pillow (magic bytes + structure), never trusted
  from the declared content type or extension alone.
- products.image_path holds a path RELATIVE to settings.media_dir.
"""

from io import BytesIO
from pathlib import Path

from loguru import logger
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ImageTooLargeError, InvalidImageError
from app.models import Product

MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_EXT_BY_FORMAT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
_MEDIA_TYPE_BY_EXT = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def _media_root() -> Path:
    return Path(settings.media_dir)


def image_file_path(product: Product) -> Path | None:
    """Absolute path of the product's stored image, if any."""
    if product.image_path is None:
        return None
    return _media_root() / product.image_path


def image_media_type(product: Product) -> str:
    ext = (product.image_path or "").rsplit(".", 1)[-1]
    return _MEDIA_TYPE_BY_EXT.get(ext, "application/octet-stream")


def _detect_format(data: bytes) -> str:
    """Return the verified Pillow format name, or raise InvalidImageError."""
    try:
        with Image.open(BytesIO(data)) as img:
            detected = img.format
            img.verify()  # structural integrity check on the real bytes
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError(reason=str(exc)) from exc
    if detected not in _EXT_BY_FORMAT:
        raise InvalidImageError(reason=f"format non supporté : {detected}")
    return detected


def save_product_image(
    db: Session, product: Product, data: bytes, content_type: str | None
) -> Product:
    """Validate and store the image, replacing (and cleaning) any old file."""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise InvalidImageError(reason=f"content-type {content_type!r}")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageTooLargeError(size=len(data), max_size=MAX_IMAGE_BYTES)
    detected = _detect_format(data)

    ext = _EXT_BY_FORMAT[detected]
    relative = f"products/{product.id}.{ext}"
    target = _media_root() / relative
    target.parent.mkdir(parents=True, exist_ok=True)

    old = image_file_path(product)
    target.write_bytes(data)
    # Replacing cleans the old file when the extension changed.
    if old is not None and old != target:
        old.unlink(missing_ok=True)

    product.image_path = relative
    db.commit()
    db.refresh(product)
    logger.info("Product image stored | product_id={} path={}", product.id, relative)
    return product


def delete_product_image(db: Session, product: Product) -> Product:
    """Remove the stored file and clear image_path (idempotent)."""
    old = image_file_path(product)
    if old is not None:
        old.unlink(missing_ok=True)
    product.image_path = None
    db.commit()
    db.refresh(product)
    return product
