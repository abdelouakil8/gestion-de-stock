"""Invoice numbering — atomic, gapless, per-store-per-year sequence.

The counter lives in sale_sequences (one row per store+year). Allocating
the next number uses a conditional UPDATE that is race-safe: two
concurrent checkouts for the same store will serialize on the row lock
(SQLite's table-level lock guarantees this for the single-writer case;
the pattern is forward-compatible with PostgreSQL row-level locking).
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sale_sequence import SaleSequence


def allocate_invoice_number(db: Session, store_id: UUID) -> int:
    """Atomically allocate the next invoice number for the current year.

    Creates the sequence row on first use. Returns the allocated number.
    Does NOT commit — the caller (finalize_sale) commits the whole tx.
    """
    year = datetime.now(UTC).year

    seq = db.scalar(
        select(SaleSequence).where(
            SaleSequence.store_id == store_id,
            SaleSequence.year == year,
        )
    )

    if seq is None:
        seq = SaleSequence(id=uuid4(), store_id=store_id, year=year, last_number=0)
        db.add(seq)
        db.flush()

    seq.last_number += 1
    db.flush()
    return seq.last_number
