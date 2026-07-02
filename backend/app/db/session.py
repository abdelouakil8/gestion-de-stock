from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

url = make_url(settings.database_url)

connect_args = {}
if url.get_backend_name() == "sqlite":
    # Sessions are used from FastAPI worker threads.
    connect_args["check_same_thread"] = False
    if url.database:
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
