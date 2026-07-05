"""Invoice numbering — atomic, gapless, per-store-per-year sequence.

The counter lives in sale_sequences (one row per store+year). Allocating
the next number uses a conditional UPDATE that is race-safe: two
concurrent checkouts for the same store will serialize on the row lock
(SQLite's table-level lock guarantees this for the single-writer case;
the pattern is forward-compatible with PostgreSQL row-level locking).
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from app.models.sale_sequence import SaleSequence


def allocate_invoice_number(db: Session, store_id: UUID) -> int:
    """Atomically allocate the next invoice number for the current year.

    Creates the sequence row on first use. Returns the allocated number.
    Does NOT commit — the caller (finalize_sale) commits the whole tx.

    The increment is keyed on the natural business key (store_id, year), NOT
    on the surrogate ``id``. Keeping the surrogate id out of the WHERE clause
    makes this immune to any id-serialization drift in the stored row (a
    legacy row could carry a dashed UUID string while the ORM binds the bare
    hex form — an id-keyed UPDATE would then silently match 0 rows and raise
    StaleDataError). SQLite serializes writers, so the read-modify-write below
    is race-safe; the pattern ports cleanly to PostgreSQL row locking later.
    """
    year = datetime.now(UTC).year

    updated = db.execute(
        update(SaleSequence)
        .where(
            SaleSequence.store_id == store_id,
            SaleSequence.year == year,
        )
        .values(last_number=SaleSequence.last_number + 1)
    )

    if updated.rowcount == 0:
        # First invoice of the year for this store — create the counter row.
        db.execute(
            insert(SaleSequence).values(
                id=uuid4(), store_id=store_id, year=year, last_number=1
            )
        )
        return 1

    return db.scalar(
        select(SaleSequence.last_number).where(
            SaleSequence.store_id == store_id,
            SaleSequence.year == year,
        )
    )
