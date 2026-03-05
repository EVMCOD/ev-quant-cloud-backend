import logging
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Import from config so the fail-fast check happens at import time.
# If DATABASE_URL is missing, startup aborts here with a clear message.
from app.core.config import DATABASE_URL

log = logging.getLogger(__name__)

# Log host/port/dbname for diagnostics — never log credentials.
_u = urlparse(DATABASE_URL)
log.info(
    "DB config: host=%s port=%s dbname=%s",
    _u.hostname,
    _u.port or 5432,
    (_u.path or "").lstrip("/"),
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # Import models so Base knows about all tables before create_all.
    from app.db import models  # noqa: F401
    log.info("Running create_all (idempotent)")
    Base.metadata.create_all(bind=engine)
