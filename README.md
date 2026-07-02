# Gestion de Stock & Point de Vente

Local-first, offline-capable POS and inventory management desktop application
for small retail merchants. Windows 10+, no internet connection required.

## Architecture

- **backend/** — FastAPI service bound to `127.0.0.1` only. All business
  logic (pricing tiers, minimum-price floor, atomic stock) lives in the
  service layer; the UI is never trusted for business rules.
- **frontend/** — PySide6 desktop UI. It never touches the database: every
  data operation goes through the local HTTP API (this keeps future mobile
  and cloud-sync additions painless).
- **backend/alembic/** — database migrations (SQLite today, PostgreSQL-ready
  by design: ORM-only access, no raw SQL).

## Prerequisites

- Windows 10 or newer
- Python 3.11+

## Setup

```powershell
# From the project root
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env
```

Optional (requires a git repository): `pre-commit install`

## Run

**Desktop app** (starts the API automatically in the background):

```powershell
python frontend\main.py
```

**API alone** (development):

```powershell
cd backend
uvicorn app.main:app --reload
```

**Database migrations:**

```powershell
cd backend
alembic upgrade head
```

**Tests / lint:**

```powershell
pytest
ruff check .
black --check .
```

## Configuration

All settings live in `.env` at the project root (see `.env.example`).
Defaults are safe: the API binds to `127.0.0.1:8765` and the SQLite database
is created under `data/pos.db`. No secrets or paths are hardcoded.

## Project structure

```
├── backend/
│   ├── alembic/            # migrations (env.py wired to app metadata)
│   ├── app/
│   │   ├── api/            # routers — thin: parse → call service → respond
│   │   ├── core/           # settings, logging, custom exceptions
│   │   ├── db/             # engine, session factory, declarative Base
│   │   ├── models/         # SQLAlchemy models (dumb — no business logic)
│   │   ├── schemas/        # Pydantic v2 schemas (money = Decimal, never float)
│   │   ├── services/       # ALL business logic
│   │   └── main.py         # FastAPI entrypoint
│   └── tests/
├── frontend/
│   ├── assets/             # images, icons, fonts
│   ├── ui/
│   │   ├── screens/        # application screens
│   │   ├── widgets/        # reusable widgets
│   │   ├── styles/         # app.qss + design tokens
│   │   └── strings.py      # centralized user-facing strings (FR)
│   └── main.py             # desktop entrypoint (boots the API, opens window)
├── .env.example
├── requirements.txt        # runtime dependencies
└── requirements-dev.txt    # dev & packaging tools
```
