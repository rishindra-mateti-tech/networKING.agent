import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

# Overridable so a deployed instance can point at a persistent volume
# (e.g. sqlite:////data/networking.db) instead of the working directory,
# which would otherwise be wiped on every redeploy.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./networking.db")

# connect_args={"check_same_thread": False} is required for SQLite in FastAPI to allow multi-threaded access.
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        # WAL lets readers and writers proceed concurrently instead of locking
        # the whole file on every write. Matters here because the queue
        # workers and the API server both hit the DB at the same time.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """Dependency to get a database session and ensure it gets closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
