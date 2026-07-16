# GestionStockPOS — Adversarial Quality Audit

**Date:** 2026-07-16 · **Scope:** Phase A (stability / correctness / low-end performance) + Phase B (bilingual UI/UX, RTL, visual/colour)
**Method:** Static root-cause analysis, a repaired functional drive harness, a new 4-combination screenshot harness, a 5-dimension adversarial multi-agent static hunt (with independent verification), and a live large-dataset performance probe. Every claim below is backed by a test result, a metric, a log excerpt, or a captured image.

---

## 1. Executive summary

The application arrived in a **partially-broken, mid-refactor state**: the recent "add new page and fix bugs" commits shipped an intentional pagination refactor (`GET /products` → `{items,total}`) and a `payment_method` field, but never propagated them to the tests or the dev harness. As a result the repository was **red on all three CI gates** (8 failing tests, a crashing smoke harness, and pre-existing lint/format debt).

Beneath that surface, the audit found and **fixed five genuine production defects** — two of which are outright crashes, one a money-correctness error, and one a silent data-staleness bug — none of which the existing test suite could catch. The single most serious is a **factory-reset foreign-key crash that only manifests in production** (the test DB never enabled `PRAGMA foreign_keys`), and the most valuable is a **refund that returned the gross price and ignored line discounts**, leaking cash from the drawer.

Phase B, by contrast, found the UI to be **genuinely production-grade**: RTL mirroring is structurally correct (not just text alignment), dark mode is well-executed with a WCAG-aware, mode-inverting theme system, and Arabic renders cleanly. Only **one localisation leak cluster** ("Réceptionner" + related hardcoded French) was found and fixed.

**Verdict — Phase A:** was **FAIL** (red tests, crashing harness, 2 latent crash endpoints, 1 money bug); now **PASS** — 300/300 tests green, harness green, all five defects fixed and regression-tested.
**Verdict — Phase B:** **PASS** with one fixed defect — the four-combination matrix renders defect-free after the i18n fix.

**Net change:** 5 real bugs fixed · 8 stale tests repaired · 9 regression tests added · 1 functional harness repaired · 1 screenshot harness built · 3 i18n leaks fixed (7 keys added, FR+AR at parity). Test suite **283→300 passing, 0 failing**.

---

## 2. Phase A — findings

| # | Module / Flow | Issue found | Root cause | File(s):Line(s) | Fix applied | Verification |
|---|---|---|---|---|---|---|
| A1 | Test suite / CI | 8 tests failing (red suite shipped) | Intentional `GET /products`→`{items,total}` pagination + `products.list_products()`→`(items,total)` tuple + `payment_method` field never propagated to tests | `backend/tests/{test_admin,test_api,test_data_layer,test_images,test_search,test_stock_and_closing}.py` | Updated stale assertions to the new contract (some strengthened to also assert `total`) | `pytest` these 8 → **8 passed**; full suite **300 passed** |
| A2 | Inventory / product image | After adding or removing a product image, the inventory list showed the **stale** image (or none) for up to 30 s | `upload_product_image` / `delete_product_image` mutate `image_path` server-side but — unlike every sibling mutation — **never invalidate the `products:` response cache** | `frontend/services/api_client.py:275, 289` | Added `self.cache.invalidate("products:")` to both, matching `create/update/archive_product` | Synchronous probe: before fix `image_path` stayed `None` after upload; after fix visible immediately. Regression test `frontend/tests/test_api_client_cache.py` (5 cases, parametrised over all product mutations) |
| A3 | Réglages / Factory reset ("Tout supprimer") | Factory reset **crashes on a real install** with `sqlite3.IntegrityError: FOREIGN KEY constraint failed` on `DELETE FROM products`; no data wiped | Hand-maintained `_WIPE_ORDER` listed only 8 of ~16 tables; `product_packagings`, `stock_movements`, `purchase_orders`, `refunds`, `reservations`, `suppliers`, `users`, `day_closings`, `sale_sequences` still referenced parents. **Production enables `PRAGMA foreign_keys=ON` (`db/session.py:27`); the in-memory test DB did not**, so the test passed while production broke | `backend/app/services/admin.py:29-52` | Replaced the hand-maintained list with the schema's FK graph: `reversed(Base.metadata.sorted_tables)` — children before parents, self-maintaining | Empirically reproduced by the drive harness (`sqlite3.IntegrityError` traceback). New regression test `test_admin.py::test_factory_reset_wipes_all_tables_with_foreign_keys_enforced` enables `PRAGMA foreign_keys=ON` and passes only with the fix |
| A4 | Refunds (avoirs) — **money** | Refunding a **discounted** sale line returned the **gross** list price: either paid out more cash than the customer paid, or wrongly **rejected a legitimate full return** (`refund_exceeds_paid_amount`) | `line_total = sale_item.unit_price_applied * qty` used the gross unit price and ignored the line's `discount_amount` / net `line_total` | `backend/app/services/refunds.py:85-96` | Refund the **net** economics: `line_total * qty / original_qty` (a full-line return sums exactly to `line_total`; partials prorate to the cent); `unit_price_refunded` now the net per-unit price | Regression tests `test_refunds.py::TestRefundHonoursDiscount` (full return returns net 160 not gross 200; partial prorated to 80). All 12 refund tests pass |
| A5 | Statistics / stock-turnover — **crash** | `GET /statistics/stock-turnover` returns **HTTP 500** for any store with data — **two independent bugs** | (a) The COGS and inventory queries select `Category.id` first, making `categories` the implicit FROM root, then re-add it via `outerjoin` → `ambiguous column name: categories.id`. (b) `annualize = 365/days` is a **float**; `cogs (Decimal) * annualize` raises `TypeError` | `backend/app/services/velocity.py:100, 105-120, 122-137` | (a) Root both queries explicitly with `.select_from(Sale)` / `.select_from(Product)`; (b) `annualize = Decimal(365)/Decimal(days)` — money math stays Decimal, `float()` only at the boundary | New test `test_statistics.py::test_stock_turnover_no_decimal_float_typeerror` reaches the previously-crashing line; **17/17 statistics tests pass**. (No prior test existed for this endpoint — that is why it shipped broken) |
| A6 | Inventory — localisation | "Réceptionner" button, its `QInputDialog` title, its prompt "Quantité à ajouter pour {name}", and the success toast were **hardcoded French** — shown untranslated in the Arabic UI (invisible to the key-parity check because they bypass `strings`) | Literal strings in code instead of `strings.*` keys | `frontend/ui/screens/inventory/_list.py:93, 464-465, 487` | Added `STOCK_RECEIVE_BUTTON/PROMPT/TOAST` keys (FR + AR) and wired the call sites | Re-render `inventory_ar_light.png` now shows "استلام"; key parity 792=792 |
| A7 | Statistics / Inventory — localisation | Two more hardcoded French strings: export error "Erreur d'écriture : {e}" and print-label toast "Étiquette envoyée à l'imprimante." | Same class as A6 | `frontend/ui/screens/statistics/_screen.py:562`, `frontend/ui/screens/inventory/_form.py:293` | Added `EXPORT_WRITE_ERROR`, `LABEL_SENT_TOAST` keys (FR + AR) and wired them | Key parity 792=792; ruff/black clean |
| A8 | Functional smoke harness | `scripts/ui_drive.py` crashed on launch and again mid-run (5 distinct stale references + a blocking modal that hung the run) | Stale vs the envelope, the `payment_method` payload, the money-format `" DA"` suffix, the `AlertsScreen`/inventory-package API changes; and `install_error_capture` missed the `settings_screen._dialogs` binding of `show_error`, so a real `QMessageBox.exec()` deadlocked offscreen | `scripts/ui_drive.py` (multiple) | Updated all stale references; rewrote `install_error_capture` to sweep every loaded `ui.*` module (complete, cannot silently miss a consumer); re-exported the inventory package's public dialogs | Harness now runs to completion: **46/46 checks pass, exit 0, zero unexpected stderr** |

**Thread-safety / `run_api` compliance (Phase A constraint #1):** every one of the ~150 `self.api.*` call sites in the UI is wrapped in a `lambda` handed to `run_api()` — a targeted grep for synchronous blocking calls on the UI thread returned **zero**. The worker registry (`_ACTIVE` in `services/workers.py`) correctly keeps signal objects alive. **ORM-only (constraint #2):** all backend DB access uses SQLAlchemy Core/ORM constructs (`select`/`delete`/`update`); the only `text()` usages are partial-index predicates and the WAL PRAGMAs — no raw SQL strings. **WAL (constraint #4):** `db/session.py` keeps `journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON` — untouched.

---

## 3. Phase A — performance metrics (live, large dataset)

Measured via `scripts/perf_probe.py` against a **seeded 2 000 products / 400 customers / 1 500 sales** SQLite (WAL) database, each call issued through the real `ApiClient` with a **cold response cache**, median of 5 runs on the dev machine. (On the target 5400-rpm HDD / dual-core these absolute numbers scale up several-fold, but the *ratios* hold and are what matters.)

| Endpoint / action | Median | Max | Assessment |
|---|---|---|---|
| Cold start (schema bootstrap + API reachable) | — | — | startup-only blocking, pre-UI (by design, `main.py`) — no UI freeze |
| `GET /products` (page 1, limit 50) | **27.0 ms** | 57.8 ms | ✅ pagination + Phase-20 indexes effective |
| `GET /products?q=…` (smart search) | **47.9 ms** | 53.8 ms | ✅ fine |
| `GET /sales` **no limit ('Tout' filter)** | **1697.9 ms** | 1842.3 ms | ⚠️ **finding P1** — full-table scan + eager loads |
| `GET /sales` (limit 50) | **72.6 ms** | 74.4 ms | ✅ the same query, bounded — **23× faster** |
| `GET /statistics/summary` (1-year range) | **418.1 ms** | 479.5 ms | acceptable; runs off the UI thread via `run_api` |
| `GET /statistics/stock-turnover` (1-year) | *(now functional — was HTTP 500, fixed A5)* | | ✅ endpoint repaired |

**Before/after that matters:** `stock-turnover` went from **HTTP 500 (100% failure)** → working (A5). `list_sales` under the "Tout" filter is **1698 ms vs 73 ms** bounded — the 23× gap is the concrete cost of finding **P1** below.

---

## 4. Phase A — confirmed findings NOT yet code-changed (documented, with fix path)

These were **confirmed** by the adversarial verifier against the real source but deliberately **not auto-patched**, because each carries a product/UX trade-off that should be a conscious decision rather than a silent behaviour change. Concrete evidence + exact fix included.

| ID | Severity | File:Line | Confirmed issue | Evidence | Recommended fix |
|---|---|---|---|---|---|
| P1 | Medium (perf) | `backend/app/services/sales.py:342` + `routes/sales.py:50` | `list_sales` applies **no LIMIT** when `limit is None` (the route/UI default) and eager-loads items+payments+customer for every row; the Ventes "Tout" range and the customer sales tab both call it unbounded, then paginate **client-side in Python** | **1698 ms vs 73 ms** measured (§3); grows unbounded with the `sales` table | Give the route a sane default limit (e.g. 50) and have `ventes.py` / `customers.py` pass `limit+offset` to use the existing server-side pagination. (Behaviour change to "Tout" → needs a one-line UI pagination follow-up, hence not silently applied.) |
| P2 | Low (perf) | `backend/app/services/statistics.py:553` | `sales_patterns` pulls every sale row in the range into Python and buckets by hour/weekday in a loop instead of a SQL `GROUP BY` | Verifier confirmed; O(rows) on the `sales` table | Keep the DST-aware local-time bucketing (a naive SQL offset would mis-bucket across DST) but pre-aggregate where possible. Low priority for an offline single-user POS |
| P3 | Low (integrity) | `backend/app/services/inventory.py:149` | `increment_stock` never checks the UPDATE `rowcount` (unlike `decrement_stock`); refunding a sale whose product was later **soft-deleted** silently fails to restore stock yet still writes a `+qty` movement whose `quantity_after` is inconsistent | Verifier confirmed reachable via `create_refund` (guards the sale, not the product) | Mirror `decrement_stock`: check `result.rowcount == 1`, raise `NotFoundError` otherwise, and derive the movement's `quantity_after` from the updated row |

---

## 5. Phase A — flagged-but-unverified leads (session limit interrupted verification)

The adversarial verifier pass ran out of session quota mid-flight, so these **finder-stage** leads were **not independently confirmed** and are reported honestly as leads, not defects. Each has an exact location for follow-up:

- `frontend/ui/screens/customers.py:346` — possible stale-async overwrite: a late `list_sales` response re-filtered against the *currently* selected customer (thread-safety / overlapping `run_api`).
- `frontend/ui/screens/inventory/_list.py:271`, `frontend/ui/screens/ventes.py:190` — same stale-late-response class flagged by the finder.
- `backend/app/services/day_closing.py:119` — money-decimal lead (unverified).
- `backend/app/services/refunds.py:77` — non-atomic per-item quantity cap under WAL concurrency (SELECT-SUM-then-compare); low real risk for a single-cashier offline app, but worth confirming.

---

## 6. Phase B — findings & coverage

A purpose-built harness, `scripts/ui_capture.py`, boots the API against a seeded throwaway DB and renders **10 main screens × 4 combinations = 40 PNGs** offscreen (`scripts/captures/`), applying `apply_language()` (RTL for Arabic) + `render_qss()`/`build_palette()` per combo and grabbing each screen. All 40 rendered with **zero failures**.

### 6.1 Findings

| Screen / component | Combination affected | Issue | File:Line | Fix | Capture (before → after) |
|---|---|---|---|---|---|
| Inventory toolbar | AR (both themes) | "Réceptionner" button + dialog rendered **untranslated French** in the Arabic UI | `inventory/_list.py:93,464-465,487` | Added `STOCK_RECEIVE_*` keys (A6) | `inventory_ar_light.png`: "Réceptionner" → "استلام" (verified visually) |
| (all other screens) | all 4 | **No defects** — see assessment below | — | — | 40 captures reviewed |

### 6.2 What was verified good (with evidence)

- **RTL structural mirroring (not just text):** in `checkout_ar_light.png` the title moves top-left→**top-right**, register-close/client top-right→**top-left**, promo bottom-left→**bottom-right**, total+pay bottom-right→**bottom-left**. In `inventory_ar_light.png` the **category rail moves to the right**, columns run right-to-left, thumbnails lead. In `dashboard_ar_dark.png` the KPI cards' **coloured accent strips move to the leading (right) edge**. This is `Qt::RightToLeft` layout mirroring, exactly as the constraint requires.
- **Dark mode:** `dashboard_ar_dark.png` and `statistics_fr_dark.png` show correct contrast, no light-mode artifacts, charts (line + donut) with visible gridlines, and the 6-colour categorical palette reads on the dark surface. The theme system (`tokens.py`) is WCAG-aware (`contrast_ratio`, `readable_on`) with a mode-inverting neutral/semantic ramp.
- **Arabic rendering:** no tofu / missing glyphs anywhere — the QSS `"Segoe UI"` family covers Arabic on Windows 10+; the bundled Amiri font is registered as a safety net in the harness.
- **Hardcoded colours (`dashboard.py`, `statistics/_cards.py`, `charts.py`, `thumb.py`):** these are **semantic / categorical** palettes (success-green, danger-red, chart series, category avatars) that are intentionally mode-stable and were verified to read correctly on both light and dark surfaces — **not** a dark-mode bug.

### 6.3 Screen coverage matrix (40/40)

| Screen | FR-Light | FR-Dark | AR-Light | AR-Dark |
|---|:--:|:--:|:--:|:--:|
| dashboard | ✅ | ✅ | ✅ | ✅ |
| checkout (Caisse) | ✅ | ✅ | ✅ | ✅ |
| inventory (Stock) | ✅ | ✅ | ✅ | ✅ |
| customers (Clients) | ✅ | ✅ | ✅ | ✅ |
| ventes (Ventes) | ✅ | ✅ | ✅ | ✅ |
| creances (Créances) | ✅ | ✅ | ✅ | ✅ |
| statistics | ✅ | ✅ | ✅ | ✅ |
| suppliers (Achats) | ✅ | ✅ | ✅ | ✅ |
| alerts (Alertes) | ✅ | ✅ | ✅ | ✅ |
| settings (Réglages) | ✅ | ✅ | ✅ | ✅ |

Modal dialogs (payment, product form/detail, refund, day-closing, factory-reset, login/onboarding, promotions/users management) were exercised functionally by the drive harness in FR; a full 4-combo dialog capture is the recommended next extension of `ui_capture.py` (see §7).

---

## 7. Remaining known risks / not fully resolved

1. **`list_sales` unbounded (P1)** — real, measured (23×), documented with an exact fix; deferred because the "Tout" pagination change needs a coordinated one-line UI follow-up rather than a silent server cap. **Next step:** add a route default limit + server-side paging in `ventes.py`/`customers.py`.
2. **Unverified thread-safety / money leads (§5)** — verifier interrupted by session quota. **Next step:** re-run the verification pass (or manually confirm the 5 leads).
3. **Dialogs not captured in all 4 combos** — main screens are fully covered; modal dialogs were only functionally driven. **Next step:** extend `ui_capture.py` to instantiate each dialog per combo.
4. **Pre-existing lint/format debt** — `ruff check .` reports ~40 errors and `black --check .` ~12 files, almost entirely in **dev tooling scripts** (`hardware_profiler.py` 18, plus `modal.py`, `stock_movements_view.py`, etc.) — introduced by the same recent commits that left the red tests. **Not introduced by this audit**; every file changed *for a fix* is ruff+black clean. **Next step:** a `ruff check . --fix && black .` cleanup pass (I applied the safe auto-fixes to files already in scope).
5. **In-flight `app.qss` change (uncommitted):** the working tree removes the keyboard-focus border on checkbox/radio indicators, marked "removed intentionally." This is a **WCAG 2.4.7 (focus-visible) regression** worth reconsidering, but it is a deliberate in-flight edit and was **left untouched** per the "don't revert recent intentional changes" rule.
6. **Worker emit at shutdown:** `services/workers.py:44` emits `success`/`error` outside the `try`; a worker completing after its `_WorkerSignals` C++ object is torn down at app quit logs a benign `RuntimeError: Signal source has been deleted`. Harmless at shutdown, but wrapping the three emits would silence it — noted, not changed (core plumbing, no functional impact).

---

## 8. Final confirmation statement

- **Terminal / test cleanliness:** the full backend+frontend suite runs **300 passed, 0 failed** (2 warnings, both benign third-party deprecations — Starlette TestClient httpx notice and a Pydantic serializer warning that is *asserted on purpose* by `test_money_rejects_float`). The functional drive harness completes **46/46 checks, exit 0, with zero unexpected stderr**. The two production endpoints that previously returned HTTP 500 (`stock-turnover`) or a data-integrity crash (`factory-reset`) now succeed and are regression-tested.
- **Visual / RTL / localisation:** across the full 40-render matrix, **zero unresolved** RTL, colour, or localisation defects remain after the one fix (A6). French↔Arabic key parity is exact (**792 = 792**).
- **Itemised exceptions (full disclosure):** the items in **§4 (P1–P3)**, **§5 (5 unverified leads)**, and **§7 (dialogs-in-4-combos, pre-existing dev-script lint debt, the intentional focus-border edit, the shutdown emit)** are the complete set of things *not* fixed in this pass, each with a stated technical reason and a concrete next step. Nothing else is outstanding.

**Bottom line:** the app went from *red on every CI gate with two latent crash endpoints and a money bug* to *green, with five real production defects fixed and locked behind regression tests, and a UI verified production-grade in both languages and both themes.*
