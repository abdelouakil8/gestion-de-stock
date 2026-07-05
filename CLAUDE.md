# CLAUDE.md — project guide for AI assistants

Local-first, offline POS + inventory desktop app for small retailers.
Windows 10+, French UI (Arabic RTL secondary). **backend/** = FastAPI service
bound to `127.0.0.1`; **frontend/** = PySide6 UI that talks to the backend only
over the local HTTP API (never touches the DB directly). All business logic
lives in `backend/app/services/`.

## Environment

Tools live in the project virtualenv `.venv` (Windows layout: `.venv/Scripts/`).
From the project root:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env
```

## Commands (run from the project root)

```powershell
pytest                # test suite (config in pyproject.toml: testpaths=backend/tests, pythonpath=backend)
ruff check .          # lint  — must be clean (zero errors)
ruff check . --fix    # auto-fix lint where possible
black .               # format in place
black --check .       # format check — must report zero files to reformat
```

Lint/format config is in `pyproject.toml` (line length 88, target py311, ruff
rules `E,F,I,UP,B`). A `.pre-commit-config.yaml` runs ruff + black on commit.

Run the desktop app: `python frontend\main.py` (it boots the API in-process).

## Security — NEVER commit these

- **`*.pem`** (RSA license-signing keys) and **`license.lic`** are git-ignored
  and must never be committed. A leaked private key was purged from history and
  the keypair rotated; the signing **private key lives outside version control**
  (local file / secrets manager only).
- The license **public** key is embedded in `frontend/services/license.py`
  (`_PUBLIC_KEY_PEM`). Rotating the keypair means regenerating it with
  `scripts/generate_license.py generate-keypair` and pasting the new public key
  there.
- `.env` (contains `PIN_HASH`) and `data/`, `media/`, `logs/` are git-ignored
  runtime state.

## Packaging / dependencies

- `requirements.txt` — loose runtime deps (`>=`), for development.
- `requirements-dev.txt` — dev + packaging tools (pytest, ruff, black, pyinstaller).
- **`requirements.lock.txt`** — fully pinned, reproducible versions. **Packaging
  builds (PyInstaller) must install from the lock file**, not the loose
  `requirements.txt`, so shipped binaries are reproducible.

## Third-party assets

Bundled fonts/assets and their licenses are tracked in
`THIRD_PARTY_LICENSES.md` (e.g. the Amiri Arabic font under the SIL OFL, with
`OFL.txt` kept next to `backend/app/assets/fonts/Amiri-Regular.ttf`).

## CI

`.github/workflows/ci.yml` runs on `windows-latest` for push/PR: installs deps,
then `ruff check .`, `black --check .`, `pytest`. Keep all three green.
