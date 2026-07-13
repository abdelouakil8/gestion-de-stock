# PostgreSQL migration guide

This application ships with SQLite for zero-config desktop use. If you
outgrow a single machine — multiple cashier stations, a remote dashboard,
or high-concurrency POS — PostgreSQL is the recommended upgrade path.

## Prerequisites

- PostgreSQL 15+ running on the local network or a managed instance
  (Supabase, RDS, etc.).
- `psycopg2-binary` (or `psycopg2`) installed in the virtualenv:
  ```
  pip install psycopg2-binary
  ```

## 1. Create the database

```sql
CREATE DATABASE pos_stock ENCODING 'UTF8' LC_COLLATE 'fr_FR.UTF-8';
CREATE USER pos_app WITH PASSWORD '<strong-password>';
GRANT ALL PRIVILEGES ON DATABASE pos_stock TO pos_app;
```

## 2. Point the application at PostgreSQL

Edit `.env` (or set the environment variable):

```
DATABASE_URL=postgresql://pos_app:<password>@<host>:5432/pos_stock
```

The SQLAlchemy engine in `backend/app/db/session.py` detects the backend
automatically — SQLite pragmas are only applied when the URL starts with
`sqlite://`.

## 3. Run migrations

```
alembic upgrade head
```

On next startup the application calls `prepare_database()` which runs
`alembic upgrade head` automatically, so a manual invocation is only
needed if you want to verify before launching.

## 4. Migrate existing data (optional)

Use `pgloader` or a custom script to dump the SQLite database and import
it into PostgreSQL:

```bash
pgloader sqlite:///data/pos.db postgresql://pos_app:<password>@<host>:5432/pos_stock
```

Verify row counts afterwards:

```sql
SELECT 'stores' AS t, count(*) FROM stores
UNION ALL SELECT 'products', count(*) FROM products
UNION ALL SELECT 'sales', count(*) FROM sales
UNION ALL SELECT 'customers', count(*) FROM customers;
```

## 5. SQLite vs PostgreSQL differences

| Area | SQLite | PostgreSQL |
|------|--------|------------|
| Concurrency | WAL mode, single-writer | Full MVCC, many writers |
| JSON | `json_extract` | `->`, `->>` operators |
| Full-text search | FTS5 (not used) | `tsvector` / `pg_trgm` |
| Constraints | CHECK, FK (pragma-enabled) | CHECK, FK (native) |
| Types | Loose affinity | Strict typing |

The ORM abstracts most differences. Two things to watch for:

1. **`Money` type** — stored as `BIGINT` (cents) on both backends;
   no change needed.
2. **`Boolean`** — SQLite stores `0`/`1`; PostgreSQL uses native `bool`.
   SQLAlchemy handles the translation transparently.

## 6. Performance tuning (PostgreSQL)

The Alembic migration `e8f9a0b1c2d3` creates composite indexes for the
hot query paths (statistics date scans, movement lookups, credit filters).
These indexes apply to both SQLite and PostgreSQL.

For PostgreSQL specifically, consider:

```sql
-- Connection pool settings (in postgresql.conf or per-connection)
SET work_mem = '16MB';
SET shared_buffers = '256MB';  -- 25% of available RAM

-- Monitor slow queries
ALTER DATABASE pos_stock SET log_min_duration_statement = 200;
```

## 7. Rollback to SQLite

Change `DATABASE_URL` back to `sqlite:///data/pos.db` in `.env` and
restart. The SQLite file is untouched during PostgreSQL use, but any
data created on PostgreSQL will not be in it.
