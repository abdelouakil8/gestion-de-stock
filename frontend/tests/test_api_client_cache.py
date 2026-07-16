"""Regression: product mutations must invalidate the cached products list.

Root cause of the original defect: ``upload_product_image`` and
``delete_product_image`` changed a product's ``image_path`` server-side but did
NOT drop the ``products:`` response cache (TTL 30 s), so the inventory list
kept showing the old image (or none) until the entry expired. Every product
mutation on :class:`ApiClient` must invalidate the ``products:`` cache.
"""

import pytest

from services.api_client import ApiClient

# The exact key list_products() writes for a default (unfiltered) page.
PRODUCTS_KEY = "products:store-1:limit=None:offset=0:cat=None"


@pytest.fixture()
def api(monkeypatch):
    # No socket is opened until a request is actually issued; we stub _request
    # so the test is fully hermetic (no server, no network).
    client = ApiClient("127.0.0.1", 0)
    monkeypatch.setattr(client, "_request", lambda *a, **k: {"id": "pid"})
    return client


def _prime(api: ApiClient) -> None:
    api.cache.set(PRODUCTS_KEY, [{"id": "pid", "image_path": None}])
    assert api.cache.get(PRODUCTS_KEY)[0] is True


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda a: a.create_product({"store_id": "s"}), id="create"),
        pytest.param(lambda a: a.update_product("pid", {}), id="update"),
        pytest.param(lambda a: a.archive_product("pid"), id="archive"),
        pytest.param(
            lambda a: a.upload_product_image("pid", b"x", "image/png", "x.png"),
            id="upload_image",
        ),
        pytest.param(lambda a: a.delete_product_image("pid"), id="delete_image"),
    ],
)
def test_product_mutations_invalidate_products_cache(api, mutate):
    _prime(api)
    mutate(api)
    hit, _ = api.cache.get(PRODUCTS_KEY)
    assert hit is False, "product mutation left a stale products list in the cache"
