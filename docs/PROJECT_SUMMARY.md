# Project Summary — Gestion de Stock & Point de Vente

Local-first, offline-capable POS + inventory desktop app for small retail
merchants. Windows 10+, French UI (Arabic RTL planned as an update), zero
internet required. This document is the complete state of the project as of
2026-07-03 (Phase 6: named price levels, customers & credit, images, alerts,
settings, analytics — Phase 7: full UI redesign, 6 screens; see docs/DESIGN.md);
a new developer (or AI session) should be able to work from it alone.

## Architecture (non-negotiable, verified)

- **API-first**: PySide6 UI ⇄ FastAPI on `127.0.0.1:8765` ⇄ SQLAlchemy ORM ⇄ SQLite.
  The UI never touches the database.
- **Every UI network call runs on a Qt worker thread** (`frontend/services/workers.py::run_api`); audited — zero UI-thread calls.
- **Business logic lives only in `backend/app/services/`**; routers are thin; models are dumb.
- **Every table**: UUID PK, `created_at`/`updated_at`, `store_id` FK (multi-tenant ready),
  `deleted_at` soft delete (financial records never hard-deleted), nullable `is_synced`/`synced_at` for future cloud sync.
- **All money is `Decimal` end-to-end.** DB storage is BIGINT integer cents via a custom
  `Money` TypeDecorator (`backend/app/db/types.py`) — SQL SUMs are exact, floats are
  rejected with an error, works identically on SQLite and PostgreSQL.

## Everything built

### Models (`backend/app/models/`)
| Model | Table | Specifics |
|---|---|---|
| Store | stores | tenant root |
| Category | categories | name, store-scoped |
| Product | products | name, barcode (indexed), cost_price, **price_detail ≥ price_gros ≥ price_super_gros** (named levels, CHECK constraint; super_gros = absolute floor), stock_quantity (CHECK ≥ 0), low_stock_threshold (default 5), image_path, is_active, category FK |
| Customer | customers | name, phone (unique per store among non-deleted, partial index), note |
| Sale | sales | total_amount, paid_amount (cache of SUM(payments), maintained transactionally), customer_id (nullable FK); `balance` = derived property; immutable financial record |
| SaleItem | sale_items | sale FK, product FK, quantity, price_level (detail\|gros\|super_gros), unit_price_applied, line_total |
| Payment | payments | sale FK, amount (CHECK > 0); append-only, one row per payment incl. the checkout one |
| StoreSettings | store_settings | 1:1 store; receipt fields (shop_name, phone, address, footer_message, show_credit_details), ui_language (fr\|ar), theme_accent (hex) |

PriceTier was **removed** in Phase 6 (named levels supersede quantity tiers; decision
and backfills documented in the migration docstring).

Migrations: `a70e8f6fcbd9` (core tables), `b41c92d7e310` (stock ≥ 0 CHECK),
`c9a1e4b7d2f0` (Phase 6: named prices backfilled from tiers + floor, price_tiers
dropped, customers/payments/store_settings created, paid_amount backfilled = total
with one historical Payment row per sale, sale_items.price_level = 'detail').
Upgrading a Phase-5 database in place is covered by `tests/test_migrations.py`.
Packaged builds bootstrap a fresh schema via ORM metadata on first run; dev uses
`alembic upgrade head`.

### Enforced business rules (`backend/app/services/`)
- **Named price levels** (`pricing.py`): each product carries price_detail /
  price_gros / price_super_gros (ordering validated at create AND partial update,
  `invalid_price_levels`); at checkout the client picks a `price_level` per line and
  the SERVER resolves the unit price — the client never sends prices.
- **Price floor = price_super_gros** (`pricing.py`): any unit price below it raises
  `PriceBelowFloorError` (`price_below_floor`) — rejected, never clamped, including
  manual overrides. DB CHECK constraint backstops the ordering.
- **Atomic stock** (`inventory.py`): single conditional UPDATE
  (`SET stock = stock - q WHERE stock >= q`) closes the check-then-write race —
  DB-level, proven by a two-session stale-read test; CHECK constraint backstop.
- **Checkout** (`sales.py::finalize_sale`): one transaction for pricing + floor +
  stock + Sale/SaleItems/Payment insert; any failure rolls back everything.
  Payment info: `{mode: full}` (default) or `{mode: partial, amount_paid, customer_id}`;
  a partial payment without a customer is rejected (`credit_requires_customer`);
  amount_paid must be ≥ 0 and < total (`invalid_payment_amount`).
- **Payments** (`payments.py`): `POST /sales/{id}/payments` records instalments;
  overpayment rejected via a conditional UPDATE (`overpayment`), same race-closing
  pattern as stock; `paid_amount` always equals SUM(payments) by construction.
- **Customers** (`customers.py`): CRUD + search (name/phone), phone unique per store
  among non-deleted (`customer_phone_exists`, partial unique index backstop);
  per-customer analytics (revenue, profit, sales count, outstanding, last purchase)
  and top-customers ranking by revenue.
- **Product images** (`images.py`): JPEG/PNG/WebP ≤ 2 MB, Pillow magic-byte
  verification; filename derives ONLY from the product UUID + detected format
  (path traversal impossible); replace/delete cleans the old file; stored under
  `MEDIA_DIR/products/`, relative path in `products.image_path`.
- **Statistics** (`statistics.py`): summary/top products; per-product windows
  (today, 7/30/365 days, all-time); calendar overview (today/week/month/year,
  local timezone → naive-UTC bounds, each with the previous period); store-scoped;
  excludes soft-deleted; exact integer-cent SUMs.
- **Market-basket analysis** (`analysis/apriori.py` + `analysis/baskets.py`):
  pure-Python Apriori (frequent itemsets + rules with support/confidence/lift);
  generic basket-provider interface so FP-Growth etc. can be added as siblings.
- **Alerts** (`alerts.py`): low-stock products (stock ≤ per-product threshold) and
  outstanding credits (oldest first, with age in days) + badge counters.
- **Settings** (`settings.py`): 1:1 store settings, lazily created with defaults;
  receipts (`receipts.py`) read them (header/footer, credit paid/remaining block
  when `show_credit_details` and partially paid).

### API (`backend/app/api/`, all under `/api/v1`, Swagger at `/docs`)
- `POST /auth/verify` — PIN gate.
- `GET|POST /stores`
- `GET|POST /categories`, `PATCH|DELETE /categories/{id}`
- `GET /products`, `GET /products/by-barcode/{barcode}`, `GET /products/{id}`,
  `GET /products/{id}/details` (owner), `POST|PATCH|DELETE /products…`,
  `POST|GET|DELETE /products/{id}/image` (upload/delete PIN-gated)
- `GET|POST /customers`, `GET|PATCH /customers/{id}`, `DELETE /customers/{id}` (PIN);
  `GET /customers?q=` searches name/phone
- `POST /sales/checkout` (payment modes), `GET /sales`, `GET /sales/{id}`,
  `POST /sales/{id}/payments`, `GET /sales/{id}/receipt` (PDF, settings-aware)
- `GET /statistics/summary|top-products|overview|products/{id}|top-customers|customers/{id}|associations` (all owner/PIN)
- `GET /alerts` (low stock + outstanding credits + badge counts)
- `GET /settings`, `PUT /settings` (PIN)

Errors: single envelope `{"error": {code, message, details}}` with French, user-safe
messages; 404 not-found, 422 validation, 409 business rejections, 401 PIN, 500 logged.
New Phase-6 error codes: `invalid_price_levels` (422), `credit_requires_customer` (409),
`invalid_payment_amount` (422), `overpayment` (409), `customer_phone_exists` (409),
`invalid_image` (422), `image_too_large` (413).
Auth: PBKDF2-SHA256-hashed PIN (`scripts/set_pin.py` → `PIN_HASH` in `.env`), checked by
the `require_owner_pin` dependency (`X-Owner-Pin` header) on product/category mutations,
image upload/delete, customer delete, settings PUT, owner product details, and every
statistics endpoint. Swapping to token auth later = replace one dependency body.

### Desktop UI (`frontend/`) — Phase 7 redesign
- **Design system** (`ui/styles/tokens.py` + `app.qss`, rationale in `docs/DESIGN.md`):
  slate neutral scale, semantic success/warning/danger with subtle variants, and a
  DYNAMIC accent — the primary color comes from the `theme_accent` store setting;
  hover/pressed/subtle/focus variants are all derived from that one hex at load time
  (`accent_palette()`), re-applied live when changed in Réglages. Typography scale
  (11→28 px), 4-px spacing grid, borders-as-elevation (no GPU effects — old hardware).
  Every control has explicit normal/hover/pressed/focus/disabled QSS states; combo/spin
  arrows are shipped SVGs (`ui/styles/assets/`).
- **Shared components**: `Badge`/`DeltaChip` (price levels, stock, credit status,
  ▲/▼ period deltas), `Thumb` (product image with colored letter fallback, async via
  `services/image_cache.py`), `show_toast` (non-blocking success feedback),
  `LoadingDots`/`EmptyState`/`StatefulStack` (every data section visibly loads and has
  a designed empty state), `PriceLevelSelector` (3-state segmented control),
  `BarChart` (hand-drawn QPainter bars), `SectionCard`/`StatCard`,
  customer picker/form and payment dialogs shared across screens.
- **Shell**: frameless window, custom title bar, sidebar with icon+label `NavButton`s
  (active indicator strip inside the layout → RTL-safe) and a live notification badge
  on Alertes (GET /alerts poll every 30 s + refresh after each sale/payment).
- **Screens** (6): **Caisse** (scan/search results with thumbnails + stock badges +
  the three prices; cart lines with thumbnail, quantity, Détail/Gros/Super gros
  selector — server resolves prices; optional customer attach; F12 → payment dialog
  full/partial, partial requires a customer, remaining balance shown; toast + receipt),
  **Stock** (thumbnail + three price columns + per-product low-stock badges; form with
  image picker/preview and LIVE price-ordering hints; double-click → product sheet with
  per-period stats + bar chart), **Clients** (search list; per-customer revenue/profit/
  sales/outstanding/last-purchase; sales history with Payée/Crédit badges; record
  payments; top-customers ranking), **Statistiques** (overview cards with
  previous-period deltas, top products with thumbnails, French association-rule cards
  from /statistics/associations), **Alertes** (low stock with jump-to-product; credits
  oldest-first with age escalation neutral→warning→danger and inline payment),
  **Réglages** (receipt fields with live preview pane, language selector — Arabic
  listed « à venir », accent swatches + custom color, PIN-gated save, live re-theme).
- Startup: embedded uvicorn on a daemon thread, health-poll, first-run store creation,
  accent fetched from /settings before the window shows, PIN login dialog, crash log at
  `%LOCALAPPDATA%/GestionStockPOS/logs/crash.log`.
- Receipts: 80mm ReportLab PDF (settings-aware since Phase 6), printed via the
  Windows `print` shell verb, temp-file path built only from the sale UUID.
- Headless verification: `python scripts/ui_drive.py` — 23 assertions driving the real
  screens against the real API (checkout levels, credit rules, alerts refresh, image
  upload, settings round-trip + live re-theme). Worker-thread audit repeated: zero
  network calls on the UI thread (all through `run_api`).

### Tests (98, all passing — `pytest`)
| File | Covers |
|---|---|
| `backend/tests/test_smoke.py` | API liveness |
| `backend/tests/test_data_layer.py` | CRUD + soft delete for every model (incl. Customer, Payment); Money exactness; float rejection |
| `backend/tests/test_business_rules.py` | price-level resolution & ordering validation (create + partial update); floor = super_gros at/below; qty 0/negative; stock to 0 vs below; multi-line rollback atomicity; race (two stale-read sessions); archived/inactive/wrong-store rejection; awkward Decimal totals; both CHECK constraints |
| `backend/tests/test_customers_and_credit.py` | phone uniqueness (per store, soft-delete aware); partial-requires-customer; amount bounds; atomic credit checkout; zero-payment credit; settlement flow; overpayment at exact boundary; Decimal balance math; paid_amount == SUM(payments); customer analytics; top customers |
| `backend/tests/test_statistics.py` | exact revenue/profit; range filter; soft-deleted excluded; top products; per-product windows (today/7/30/365/all-time); calendar overview with previous periods (timezone-proof) |
| `backend/tests/test_apriori.py` | hand-verifiable supports/confidences/lifts; filtering; 3-way itemsets; param validation; basket provider grouping + soft-delete exclusion |
| `backend/tests/test_alerts.py` | threshold boundaries; inactive/archived exclusion; oldest-first credits with age; badge counters; store scoping |
| `backend/tests/test_settings.py` | lazy defaults; round-trip; partial update; language/hex validation |
| `backend/tests/test_images.py` | upload/serve/replace/delete with file cleanup; bad type; spoofed magic bytes; oversize (413); path traversal impossible; PIN |
| `backend/tests/test_api.py` | happy path over HTTP; hostile-client attempts (below floor, oversell, fake price level, credit without customer, overpay); PIN enforcement; cost_price never in cashier responses; cost_price required at creation; Swagger/openapi completeness |
| `backend/tests/test_receipts.py` | 40-line receipts; long/accented names; non-Latin degradation; settings header/footer; credit paid/remaining block on/off |
| `backend/tests/test_migrations.py` | `upgrade head` from scratch; Phase-5 DB upgraded in place with documented backfills; downgrade round-trip |

Plus `docs/UI_CHECKLIST.md` — click-through checklist, verified by a headless functional
drive of the real screens against the real API (tier reprice, checkout, oversell error
path, filters, dashboard).

### Security review (Phase 5, confirmed)
1. ✅ API binds only to loopback — enforced by a validator that rejects any non-127.x host; grep found no `0.0.0.0` anywhere; live bind check showed `127.0.0.1`.
2. ✅ Business rules cannot be bypassed from outside the UI — deliberate raw-HTTP below-floor and oversell attempts both rejected with 409 (also covered by tests).
3. ✅ No raw/concatenated SQL (grep: no `text(`, no f-string execute) — 100% ORM.
4. ✅ No hardcoded secrets/paths (grep clean); everything via `.env` + computed roots; PIN stored only as salted PBKDF2 hash.
5. ✅ Every endpoint validates via Pydantic before the service layer.
6. ✅ Receipt paths built from the sale UUID only, in the temp dir — no user input in paths.
7. ✅ `.env` git-ignored; `.env.example` up to date (API host/port, DATABASE_URL, LOG_LEVEL, PIN_HASH).

### Packaging
- PyInstaller `--onedir --windowed` → `dist/GestionStockPOS/` (~149 MB), verified on a
  clean `%LOCALAPPDATA%` profile: schema bootstrap, store creation, UI open/close, exit 0.
  Mutable state (DB, logs, .env) lives in `%LOCALAPPDATA%\GestionStockPOS`, never Program Files.
- Inno Setup script: `installer/GestionStockPOS.iss` (French installer, Start Menu +
  optional desktop icon, clean uninstall preserving user data, MinVersion 10.0).

## Known limitations / rough edges
- **Inno Setup is not installed on this machine** — the `.iss` is ready but uncompiled.
  Install Inno Setup 6 (`winget install JRSoftware.InnoSetup`) then run
  `ISCC.exe installer\GestionStockPOS.iss`.
- **Low-spec machine/VM verification is pending** — the packaged build is verified on the
  dev machine only. Windows 7/8 is impossible by design (stack requires Win10+, decided earlier).
- Receipt printing uses the shell `print` verb — requires a PDF handler with a print verb
  (present on stock Windows 10/11); a direct-to-thermal ESC/POS path may be wanted later.
- Arabic text on receipts degrades to `?` until a TTF font + text shaping is added (French is fine).
- Packaged builds bootstrap fresh schemas via ORM metadata; a future release that alters
  the schema must ship Alembic migrations and run them programmatically at startup.
- A one-pass human visual click-through (window dragging feel, dialogs, printing on real
  hardware) is recommended; all logic paths are machine-verified in `docs/UI_CHECKLIST.md`.
- Sales history has no UI screen yet (API exists: `GET /sales`).

## Intentionally NOT built (and what's already in place for each)
- **Cloud sync** — not built. Ready: nullable `is_synced`/`synced_at` on every table,
  UUID PKs (merge-safe), soft deletes (tombstones), API-first design.
- **Companion mobile app** — not built. Ready: every operation is already an HTTP API with
  Pydantic schemas; barcode lookup endpoint exists; auth dependency is swappable for tokens.
- **Multi-tenant SaaS / multi-store switcher UI** — not built. Ready: `store_id` on every
  table and every query; no code assumes a single store (verified by store-scoping tests).
- **FP-Growth and other basket algorithms** — not built. Ready: `services/analysis/`
  exposes a generic baskets-in → rules-out interface; Apriori is the first sibling.

## Recommended next steps (priority order)
1. Compile the installer with Inno Setup and test install/uninstall on a clean low-spec
   Windows 10 machine or VM (final DoD item that needs real hardware).
2. Human visual pass over `docs/UI_CHECKLIST.md` on the packaged build.
3. Commit the work (nothing has been committed; working tree contains the whole project).
4. Sales-history screen (list + detail + reprint receipt) — API already serves it.
5. Programmatic Alembic upgrades at packaged-app startup (needed before the first
   schema-changing release).
6. Arabic RTL update: QTranslator-based i18n (strings already centralized), Arabic TTF +
   shaping for receipts, `setLayoutDirection` (layouts already verified RTL-safe).
7. ESC/POS direct thermal printing as an alternative to the shell print verb.
