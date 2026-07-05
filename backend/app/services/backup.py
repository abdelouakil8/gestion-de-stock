"""Backup & restore — ZIP archive of the SQLite database and media folder.

The backup is the merchant's ONLY safety net against disk failure, theft, or
accidental factory-reset. A single ZIP bundles the database file (pos.db) and
the entire media/ tree (product images). Restoring always creates a safety
backup of the current state first, so even a bad restore is reversible.
"""

import ntpath
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from loguru import logger

from app.core.config import RUNTIME_DIR, settings

_BACKUP_DB_NAME = "pos.db"
_BACKUP_MEDIA_DIR = "media"
_SAFETY_PREFIX = "safety_before_restore_"


def _db_path() -> Path:
    """Resolve the physical SQLite file from the database_url setting."""
    url = settings.database_url
    if url.startswith("sqlite:///"):
        return Path(url.removeprefix("sqlite:///"))
    return RUNTIME_DIR / "data" / "pos.db"


def create_backup(target_dir: Path | None = None) -> Path:
    """Create a timestamped backup ZIP in target_dir (default: RUNTIME_DIR/backups).

    Uses SQLite's online backup API to get a consistent snapshot without
    locking out concurrent readers/writers.

    Returns the path to the created ZIP file.
    """
    if target_dir is None:
        target_dir = RUNTIME_DIR / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    zip_path = target_dir / f"backup_{timestamp}.zip"

    db_file = _db_path()
    media_root = Path(settings.media_dir)

    tmp_path = Path(tempfile.mkdtemp())
    try:
        tmp_db = tmp_path / _BACKUP_DB_NAME

        # SQLite online backup — consistent snapshot, no WAL issues.
        if db_file.is_file():
            src_conn = sqlite3.connect(str(db_file))
            dst_conn = sqlite3.connect(str(tmp_db))
            src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if tmp_db.is_file():
                zf.write(tmp_db, _BACKUP_DB_NAME)
            if media_root.is_dir():
                for file in media_root.rglob("*"):
                    if file.is_file():
                        rel = file.relative_to(media_root).as_posix()
                        arcname = f"{_BACKUP_MEDIA_DIR}/{rel}"
                        zf.write(file, arcname)
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)

    logger.info("Backup created | path={} size={}", zip_path, zip_path.stat().st_size)
    # Retention: prune the oldest backups in this directory so they don't grow
    # without bound on the merchant's disk.
    cleanup_old_backups(backup_dir=target_dir)
    return zip_path


def validate_backup(zip_path: Path) -> bool:
    """Quick sanity check: the ZIP must contain pos.db at minimum."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            return _BACKUP_DB_NAME in names
    except (zipfile.BadZipFile, OSError):
        return False


def _reject_unsafe_entries(zf: zipfile.ZipFile, dest: Path) -> None:
    """Guard against Zip Slip / path traversal before extraction.

    A tampered backup ZIP could carry entries like ``../../evil`` or an
    absolute path that, once extracted, would clobber files anywhere on disk.
    We accept ONLY the expected payload — the top-level ``pos.db`` and files
    under ``media/`` — and reject the entire restore (raising ``ValueError``)
    before a single byte is written.
    """
    dest_resolved = dest.resolve()
    for info in zf.infolist():
        name = info.filename
        norm = name.replace("\\", "/")
        parts = PurePosixPath(norm).parts
        # Absolute path (POSIX or Windows-drive) or parent-dir traversal.
        if norm.startswith("/") or ntpath.isabs(name) or ".." in parts:
            raise ValueError(f"Archive rejetée — entrée de chemin non sûre : {name!r}")
        # Whitelist the expected backup payload only.
        is_db = norm == _BACKUP_DB_NAME
        is_media = norm == _BACKUP_MEDIA_DIR or norm.startswith(f"{_BACKUP_MEDIA_DIR}/")
        if not (is_db or is_media):
            raise ValueError(f"Archive rejetée — entrée inattendue : {name!r}")
        # Belt-and-suspenders: the resolved target must stay inside dest.
        target = (dest_resolved / norm).resolve()
        if target != dest_resolved and dest_resolved not in target.parents:
            raise ValueError(
                f"Archive rejetée — chemin hors du dossier cible : {name!r}"
            )


def restore_backup(zip_path: Path) -> Path:
    """Replace the current database and media with the contents of the ZIP.

    ALWAYS creates a safety backup of the current state first — so even a
    botched restore can be undone by restoring the safety archive.

    Returns the path to the safety backup (so the caller can inform the user).
    Raises ValueError on invalid archive.
    """
    if not validate_backup(zip_path):
        raise ValueError("Archive invalide — le fichier pos.db est manquant.")

    # Safety backup of current state before overwriting.
    safety_dir = RUNTIME_DIR / "backups" / "safety"
    safety_dir.mkdir(parents=True, exist_ok=True)
    safety_path = create_backup(safety_dir)
    logger.warning("Safety backup before restore | path={}", safety_path)

    db_file = _db_path()
    media_root = Path(settings.media_dir)

    with zipfile.ZipFile(zip_path, "r") as zf:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Validate every entry BEFORE extracting anything (Zip Slip guard).
            _reject_unsafe_entries(zf, tmp_path)
            zf.extractall(tmp_path)

            # Replace database.
            extracted_db = tmp_path / _BACKUP_DB_NAME
            if extracted_db.is_file():
                db_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(extracted_db, db_file)

            # Replace media.
            extracted_media = tmp_path / _BACKUP_MEDIA_DIR
            if extracted_media.is_dir():
                if media_root.is_dir():
                    shutil.rmtree(media_root, ignore_errors=True)
                shutil.copytree(extracted_media, media_root)

    logger.warning("Restore completed from | archive={}", zip_path)
    return safety_path


def list_backups(backup_dir: Path | None = None) -> list[dict]:
    """List existing backup ZIPs, newest first."""
    if backup_dir is None:
        backup_dir = RUNTIME_DIR / "backups"
    if not backup_dir.is_dir():
        return []
    backups = []
    for f in sorted(backup_dir.glob("backup_*.zip"), reverse=True):
        backups.append(
            {
                "filename": f.name,
                "path": str(f),
                "size_bytes": f.stat().st_size,
                "created_at": datetime.fromtimestamp(
                    f.stat().st_mtime, tz=UTC
                ).isoformat(),
            }
        )
    return backups


def cleanup_old_backups(keep: int = 14, backup_dir: Path | None = None) -> int:
    """Remove the oldest backups beyond `keep` count. Returns deleted count."""
    if backup_dir is None:
        backup_dir = RUNTIME_DIR / "backups"
    if not backup_dir.is_dir():
        return 0
    files = sorted(backup_dir.glob("backup_*.zip"), reverse=True)
    removed = 0
    for f in files[keep:]:
        f.unlink(missing_ok=True)
        removed += 1
    if removed:
        logger.info("Cleaned up {} old backups", removed)
    return removed
