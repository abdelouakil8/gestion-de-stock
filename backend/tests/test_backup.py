"""Tests for the backup/restore service — round-trip, validation, cleanup."""

import zipfile

import pytest

from app.services import backup


@pytest.fixture()
def tmp_runtime(monkeypatch, tmp_path):
    """Point backup paths at a temp directory with a real SQLite DB."""
    import sqlite3

    db_dir = tmp_path / "data"
    db_dir.mkdir()
    db_file = db_dir / "pos.db"
    # Create a real SQLite file (backup API requires it).
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE test_marker (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO test_marker VALUES (42)")
    conn.commit()
    conn.close()

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "img1.jpg").write_bytes(b"\xff\xd8\xff\xe0fake jpeg")
    sub = media_dir / "thumbs"
    sub.mkdir()
    (sub / "thumb1.webp").write_bytes(b"fake webp")

    monkeypatch.setattr(
        "app.services.backup.settings",
        type("S", (), {
            "database_url": f"sqlite:///{db_file.as_posix()}",
            "media_dir": str(media_dir),
        })(),
    )
    monkeypatch.setattr("app.services.backup.RUNTIME_DIR", tmp_path)
    return tmp_path


class TestCreateBackup:
    def test_creates_zip(self, tmp_runtime):
        zip_path = backup.create_backup()
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"

    def test_contains_db_and_media(self, tmp_runtime):
        zip_path = backup.create_backup()
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert "pos.db" in names
            assert any("media/" in n for n in names)
            assert any("img1.jpg" in n for n in names)
            assert any("thumb1.webp" in n for n in names)

    def test_custom_target_dir(self, tmp_runtime):
        custom = tmp_runtime / "custom_backups"
        zip_path = backup.create_backup(target_dir=custom)
        assert custom.is_dir()
        assert zip_path.parent == custom


class TestValidateBackup:
    def test_valid(self, tmp_runtime):
        zip_path = backup.create_backup()
        assert backup.validate_backup(zip_path) is True

    def test_invalid_no_db(self, tmp_path):
        bad_zip = tmp_path / "bad.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("random.txt", "not a backup")
        assert backup.validate_backup(bad_zip) is False

    def test_invalid_not_zip(self, tmp_path):
        not_zip = tmp_path / "not.zip"
        not_zip.write_text("definitely not a zip file")
        assert backup.validate_backup(not_zip) is False


class TestRestoreBackup:
    def test_round_trip(self, tmp_runtime):
        import sqlite3

        zip_path = backup.create_backup()

        # Modify DB to simulate data change.
        db_file = tmp_runtime / "data" / "pos.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("DELETE FROM test_marker")
        conn.execute("INSERT INTO test_marker VALUES (99)")
        conn.commit()
        conn.close()

        safety = backup.restore_backup(zip_path)
        assert safety.exists()
        # DB should be back to the original (marker=42).
        conn = sqlite3.connect(str(db_file))
        row = conn.execute("SELECT id FROM test_marker").fetchone()
        conn.close()
        assert row[0] == 42

    def test_safety_backup_created(self, tmp_runtime):
        zip_path = backup.create_backup()
        safety = backup.restore_backup(zip_path)
        assert safety.exists()
        assert "safety" in str(safety)

    def test_invalid_archive_raises(self, tmp_path, tmp_runtime):
        bad = tmp_path / "bad.zip"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("nope.txt", "garbage")
        with pytest.raises(ValueError, match="invalide"):
            backup.restore_backup(bad)


class TestCleanup:
    def test_keeps_n_newest(self, tmp_runtime):
        backup_dir = tmp_runtime / "backups"
        backup_dir.mkdir(exist_ok=True)
        for i in range(5):
            (backup_dir / f"backup_2026070{i}_120000.zip").write_text(f"b{i}")
        removed = backup.cleanup_old_backups(keep=3, backup_dir=backup_dir)
        assert removed == 2
        remaining = list(backup_dir.glob("backup_*.zip"))
        assert len(remaining) == 3
