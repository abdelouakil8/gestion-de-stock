"""Product image cache — fetch once per product, share QPixmaps everywhere.

Fetching happens on worker threads (run_api); QPixmap construction happens
in the callback, i.e. on the UI thread, as Qt requires. Products without an
image_path never hit the network (the thumbnail shows a letter fallback).
"""

from collections.abc import Callable

from PySide6.QtGui import QPixmap

from services.workers import run_api

_api = None
_pixmaps: dict[str, QPixmap | None] = {}
_pending: dict[str, list[Callable[[QPixmap | None], None]]] = {}


def init(api) -> None:
    global _api
    _api = api


def invalidate(product_id: str) -> None:
    """Call after uploading/removing an image so thumbs refetch."""
    _pixmaps.pop(product_id, None)


def get(product: dict, callback: Callable[[QPixmap | None], None]) -> None:
    """Deliver the product's QPixmap (or None) to `callback`, async.

    The callback always runs on the UI thread; it may run immediately
    when the image is already cached or the product has no image.
    """
    product_id = product["id"]
    if not product.get("image_path"):
        callback(None)
        return
    if product_id in _pixmaps:
        callback(_pixmaps[product_id])
        return
    if product_id in _pending:
        _pending[product_id].append(callback)
        return
    _pending[product_id] = [callback]

    def on_bytes(data: object) -> None:
        pixmap = QPixmap()
        if isinstance(data, bytes) and data:
            pixmap.loadFromData(data)
        result = pixmap if not pixmap.isNull() else None
        _pixmaps[product_id] = result
        for waiting in _pending.pop(product_id, []):
            waiting(result)

    def on_error(_err: object) -> None:
        _pixmaps[product_id] = None
        for waiting in _pending.pop(product_id, []):
            waiting(None)

    run_api(lambda: _api.get_product_image(product_id), on_bytes, on_error)
