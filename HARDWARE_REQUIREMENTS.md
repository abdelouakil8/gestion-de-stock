# Hardware Requirements

This document outlines the Minimum and Recommended hardware requirements for deploying the local-first POS application in production.

The requirements have been determined through empirical data gathered via an automated stress test (`scripts/hardware_profiler.py`).

## Stress Test Methodology

To accurately simulate a high-volume production environment, the profiling script performed the following:

1. **Massive Dataset Seeding**: Populated a local SQLite database with **50,000 products**, **100,000 sales transactions**, **100,000 sale items**, and **100,000 payment records** — representing years of heavy store activity.

2. **Heavy Concurrent Load**: Simulated 10 concurrent workers firing a realistic mix of operations:
   - **Checkout** (writes with price resolution, stock decrement)
   - **Smart search** (RapidFuzz fuzzy text search across 50k products)
   - **Barcode lookup** (indexed scan)
   - **Statistics overview** (aggregation over 100k+ transactions across 5 time periods)
   - **Top products** (ranked aggregation query)
   - **Apriori market-basket analysis** (the heaviest read — frequent-itemset mining)
   - **Alerts** (low-stock + credit summary)
   - **Sales & customer list queries**

3. **Resource Monitoring**: Tracked actual CPU, RAM, and system-wide Disk I/O consumption at 500ms intervals using `psutil` over the full test duration (~8 minutes).

## Empirical Profiling Results

The test was conducted on a machine with the following specifications:
- **Host**: 8 logical CPUs (4 cores / 8 threads), 7.4 GB total RAM
- **Storage**: NVMe SSD
- **OS**: Windows 10

| Metric | Value |
|---|---|
| **Database footprint** | **105.7 MB** (50k products + 100k transactions) |
| **Test duration** | 489 seconds (8.2 min) |
| **Total API calls** | 500 (all successful, 0 errors) |

### CPU Utilization

| Percentile | Value | Meaning |
|---|---|---|
| Average | **513.6%** (~5.1 cores) | Sustained multi-core usage during mixed load |
| 95th percentile | **665.0%** (~6.7 cores) | Sustained peak under heavy mixed load |
| Maximum | **733.6%** (~7.3 cores) | Burst when statistics + checkout + search overlap |

**Key insight**: The application is aggressively parallel. The Apriori market-basket algorithm, statistical aggregations, and RapidFuzz fuzzy searches all run their heaviest work on separate threads, effectively saturating 5–7 cores when contention is highest.

### RAM Consumption

| Percentile | Value |
|---|---|
| Average | **310.6 MB** |
| 95th percentile | **357.4 MB** |
| Maximum | **422.8 MB** |

**Key insight**: The backend (FastAPI + SQLAlchemy + uvicorn) has a modest memory footprint. The 310 MB average includes Python interpreter overhead, ORM session cache, and the SQLite page cache. This does **not** include the PySide6 frontend, which adds approximately 100–200 MB when running (tested in isolation).

### Disk I/O (System-wide, during test)

| Metric | Value |
|---|---|
| Total read | **7,320 MB** |
| Total write | **7,920 MB** |

**Key insight**: The high I/O is driven by SQLite WAL (Write-Ahead Logging) checkpointing and the Apriori algorithm's intermediate result materialisation. An **SSD is strictly required**; an HDD would become a severe bottleneck.

### SQLite Concurrency Bottleneck

The stress test revealed a critical architectural constraint: **SQLite serialises all writes**. Under 10 concurrent workers, the `checkout` operation had to be protected by a mutex to avoid `database is locked` errors. In production with multiple concurrent cash registers, this limits throughput to approximately **1 checkout per 6–10 seconds** on SQLite. For multi-terminal setups, PostgreSQL migration (already anticipated in the schema's naming conventions) is strongly advised.

---

## Minimum Hardware Requirements

These specifications are suitable for a **single-terminal setup** (e.g., a standalone cash register) handling normal daily traffic.

| Component | Requirement | Justification |
|---|---|---|
| **CPU** | **2 cores** (e.g., Intel Celeron, Core i3, AMD A-series) | A single operator drives the UI and one checkout at a time. The backend runs on background threads; dual-core is sufficient for smooth UI interaction while statistics compute in the background. |
| **RAM** | **4 GB** | Backend peaked at ~423 MB under extreme load + frontend ~200 MB = ~620 MB for the application. Windows 10/11 needs ~2 GB. 4 GB gives comfortable headroom. |
| **Storage** | **64 GB SSD** (SATA SSD acceptable) | 105 MB database for years of data. 64 GB covers OS, app binaries, media files, and decades of transactions. **HDD is NOT acceptable** — SQLite WAL mode requires low write latency. |
| **Screen** | 1366×768 or higher | The POS checkout screen and statistics dashboard are designed for at least 768p vertical resolution. |
| **OS** | Windows 10 64-bit or later | PySide6 and the packaged executable are built for Windows. |

## Recommended Hardware Requirements

These specifications are ideal for **high-volume stores** (>500 transactions/day), **multi-terminal setups** (2–3 cash registers sharing a single database via network share), or stores that actively use **statistics / market-basket analysis** during peak hours.

| Component | Requirement | Justification |
|---|---|---|
| **CPU** | **4–6 cores** (e.g., Intel Core i5/i7, AMD Ryzen 5/7) | Under heavy concurrent load the app uses 5–7 cores. Quad-core ensures statistics (overview, top-products, Apriori) and checkout never contend to the point of perceptible UI lag. |
| **RAM** | **8 GB** | Extra RAM allows the OS to cache the entire SQLite database file (~106 MB) in memory, turning every query into a memory-speed operation. Also leaves room for multiple browser tabs (for online dashboards) and other office software. |
| **Storage** | **256 GB NVMe SSD** | NVMe provides 5–10× higher IOPS than SATA SSD. The stress test wrote nearly 8 GB of data in 8 minutes; NVMe ensures zero disk queuing during peak trading hours. 256 GB allows for years of data, media files, and backup archives. |
| **Screen** | 1920×1080 or higher | The statistics dashboard, customer management, and product inventory screens benefit from full HD resolution. |
| **Network** | Gigabit Ethernet (for multi-terminal setups) | When multiple terminals share the SQLite database over a network share, latency matters. Wi-Fi can cause `database is locked` errors under concurrent writes. |
| **OS** | Windows 11 Pro or Windows 10 Pro | Pro edition allows deferred updates and group policy controls for kiosk-mode operation. |

## Upgrade Path: When to Move to PostgreSQL

- **Signs you've outgrown SQLite**: Frequent `database is locked` errors with 4+ concurrent registers; database file exceeds 1 GB; backup/restore takes > 10 minutes.
- **Migration path**: The schema already uses `BIGINT` for monetary columns, a naming convention compatible with PostgreSQL, and Alembic migrations. Migration requires only changing the `DATABASE_URL` environment variable and running `alembic upgrade head`.
- **PostgreSQL hardware**: Minimum 2 GB RAM + 20 GB SSD for the database server; can run on the same machine or a local server.

---

*Last updated: 2026-07-07 | Generated from `scripts/hardware_profiler.py` empirical data.*
