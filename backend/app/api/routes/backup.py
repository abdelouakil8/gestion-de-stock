"""Backup & restore API routes — all PIN-gated (owner-only operations)."""

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import OwnerPinDep
from app.services import backup

router = APIRouter()


class BackupInfo(BaseModel):
    filename: str
    path: str
    size_bytes: int
    created_at: str


class RestoreResult(BaseModel):
    safety_backup: str
    message: str


@router.post("/create", response_class=FileResponse, dependencies=[OwnerPinDep])
def create_backup_endpoint():
    """Create a full backup and return the ZIP file for download."""
    zip_path = backup.create_backup()
    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=zip_path.name,
    )


@router.post("/restore", response_model=RestoreResult, dependencies=[OwnerPinDep])
async def restore_backup_endpoint(file: Annotated[UploadFile, File()]):
    """Upload a backup ZIP and restore it. Returns safety backup path.

    The server MUST be restarted after a successful restore (the database
    connection pool points at the old file contents).
    """
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        safety = backup.restore_backup(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return RestoreResult(
        safety_backup=str(safety),
        message=(
            "Restauration réussie. Une sauvegarde de sécurité a été créée. "
            "L'application doit être redémarrée."
        ),
    )


@router.get("/list", response_model=list[BackupInfo], dependencies=[OwnerPinDep])
def list_backups_endpoint():
    """List available backups, newest first."""
    return backup.list_backups()
