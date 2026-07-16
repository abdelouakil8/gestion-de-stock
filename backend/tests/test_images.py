"""Phase 6 product images: upload validation (type, size, magic bytes),
UUID-only filenames (path traversal impossible), replace/delete cleanup,
serving, and PIN gating."""

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.core.config import settings
from app.core.security import hash_pin
from app.main import app
from app.models import Base

PIN = "1234"
PIN_HEADER = {"X-Owner-Pin": PIN}


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """TestClient with a fresh in-memory DB, a known PIN and a temp media dir."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    monkeypatch.setattr(settings, "pin_hash", hash_pin(PIN))
    monkeypatch.setattr(settings, "media_dir", tmp_path / "media")
    app.dependency_overrides[deps.get_db] = lambda: session
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def make_product(client) -> dict:
    store = client.post("/api/v1/stores", json={"name": "Boutique Image"}).json()
    return client.post(
        "/api/v1/products",
        json={
            "store_id": store["id"],
            "name": "Eau minérale",
            "cost_price": "25.00",
            "price_detail": "40.00",
            "price_gros": "37.50",
            "price_super_gros": "30.00",
            "stock_quantity": 10,
        },
        headers=PIN_HEADER,
    ).json()


def image_bytes(fmt: str, size=(32, 32)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color=(200, 60, 30)).save(buffer, format=fmt)
    return buffer.getvalue()


def upload(
    client, product_id, data, content_type, filename="photo.png", headers=PIN_HEADER
):
    return client.post(
        f"/api/v1/products/{product_id}/image",
        files={"file": (filename, data, content_type)},
        headers=headers,
    )


def media_files(tmp_path) -> list[Path]:
    root = tmp_path / "media"
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


def test_upload_serve_replace_and_delete(client, tmp_path):
    product = make_product(client)

    png = image_bytes("PNG")
    response = upload(client, product["id"], png, "image/png")
    assert response.status_code == 201
    assert response.json()["image_path"] == f"products/{product['id']}.png"
    files = media_files(tmp_path)
    assert [f.name for f in files] == [f"{product['id']}.png"]

    served = client.get(f"/api/v1/products/{product['id']}/image")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.content == png

    # Replacing with a JPEG cleans the old PNG file.
    jpeg = image_bytes("JPEG")
    response = upload(client, product["id"], jpeg, "image/jpeg", filename="new.jpg")
    assert response.status_code == 201
    assert response.json()["image_path"] == f"products/{product['id']}.jpg"
    assert [f.name for f in media_files(tmp_path)] == [f"{product['id']}.jpg"]

    # WebP accepted as well.
    webp = image_bytes("WEBP")
    assert upload(client, product["id"], webp, "image/webp").status_code == 201
    assert [f.name for f in media_files(tmp_path)] == [f"{product['id']}.webp"]

    # Delete cleans the file and the column.
    deleted = client.delete(
        f"/api/v1/products/{product['id']}/image", headers=PIN_HEADER
    )
    assert deleted.status_code == 204
    assert media_files(tmp_path) == []
    assert client.get(f"/api/v1/products/{product['id']}/image").status_code == 404
    listed = client.get(
        "/api/v1/products", params={"store_id": product["store_id"]}
    ).json()
    assert listed["items"][0]["image_path"] is None


def test_bad_content_type_rejected(client, tmp_path):
    product = make_product(client)
    response = upload(client, product["id"], image_bytes("PNG"), "image/gif")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_image"
    assert media_files(tmp_path) == []


def test_content_not_matching_magic_bytes_rejected(client, tmp_path):
    """Declared PNG but the bytes are not an image — Pillow says no."""
    product = make_product(client)
    response = upload(client, product["id"], b"<script>alert(1)</script>", "image/png")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_image"
    assert media_files(tmp_path) == []


def test_oversize_rejected(client, tmp_path):
    product = make_product(client)
    # Valid PNG header followed by padding: past the 2 MB cap.
    payload = image_bytes("PNG") + b"\0" * (2 * 1024 * 1024)
    response = upload(client, product["id"], payload, "image/png")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "image_too_large"
    assert media_files(tmp_path) == []


def test_filename_never_trusted_path_traversal_impossible(client, tmp_path):
    product = make_product(client)
    response = upload(
        client,
        product["id"],
        image_bytes("PNG"),
        "image/png",
        filename="../../../../evil.png",
    )
    assert response.status_code == 201
    # The stored name derives from the product UUID only; nothing escaped
    # the media directory.
    assert response.json()["image_path"] == f"products/{product['id']}.png"
    assert [f.name for f in media_files(tmp_path)] == [f"{product['id']}.png"]
    assert not (tmp_path / "evil.png").exists()


def test_upload_requires_pin_and_product_must_exist(client):
    product = make_product(client)
    no_pin = upload(client, product["id"], image_bytes("PNG"), "image/png", headers={})
    assert no_pin.status_code == 401

    missing = upload(
        client,
        "00000000-0000-0000-0000-000000000000",
        image_bytes("PNG"),
        "image/png",
    )
    assert missing.status_code == 404
