"""Phase 6 store settings: lazy defaults, round-trip, validation, PIN."""

from uuid import uuid4

import pytest

from app.core.exceptions import NotFoundError
from app.schemas.settings import SettingsUpdate
from app.schemas.store import StoreCreate
from app.services import settings as settings_service
from app.services import stores


def test_get_creates_defaults_once(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Réglages"))
    row = settings_service.get_settings(db, store.id)
    assert row.shop_name is None
    assert row.show_credit_details is True
    assert row.ui_language == "fr"
    assert row.theme_accent == "#2563EB"

    again = settings_service.get_settings(db, store.id)
    assert again.id == row.id  # same row, not a duplicate


def test_get_settings_unknown_store_rejected(db):
    with pytest.raises(NotFoundError):
        settings_service.get_settings(db, uuid4())


def test_update_round_trip(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Réglages"))
    settings_service.update_settings(
        db,
        store.id,
        SettingsUpdate(
            shop_name="Chez Wakil",
            phone="0550 12 34 56",
            address="12 rue du Marché, Alger",
            footer_message="À bientôt !",
            show_credit_details=False,
            ui_language="ar",
            theme_accent="#A1B2C3",
        ),
    )
    row = settings_service.get_settings(db, store.id)
    assert row.shop_name == "Chez Wakil"
    assert row.phone == "0550 12 34 56"
    assert row.address == "12 rue du Marché, Alger"
    assert row.footer_message == "À bientôt !"
    assert row.show_credit_details is False
    assert row.ui_language == "ar"
    assert row.theme_accent == "#A1B2C3"

    # Partial update touches only the submitted field.
    settings_service.update_settings(db, store.id, SettingsUpdate(ui_language="fr"))
    row = settings_service.get_settings(db, store.id)
    assert row.ui_language == "fr" and row.shop_name == "Chez Wakil"


def test_schema_validation_rejects_bad_values():
    with pytest.raises(ValueError):
        SettingsUpdate(ui_language="en")  # only fr | ar
    with pytest.raises(ValueError):
        SettingsUpdate(theme_accent="red")
    with pytest.raises(ValueError):
        SettingsUpdate(theme_accent="#12345")  # too short
    assert SettingsUpdate(theme_accent="#abcDEF").theme_accent == "#abcDEF"
