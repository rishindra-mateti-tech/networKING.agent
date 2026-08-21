import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

# Overridable so a deployed instance can point at a real hosted database
# (Postgres) instead of a local file, which would otherwise be wiped on
# every restart on hosts with no persistent disk (e.g. Render's free tier).
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./networking.db")

# Some hosts (Render, Heroku-style) still hand out "postgres://" URLs, but
# SQLAlchemy's psycopg driver requires the "postgresql://" scheme.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_SQLITE = DATABASE_URL.startswith("sqlite")

# connect_args={"check_same_thread": False} is required for SQLite in FastAPI to allow multi-threaded access.
# Postgres needs no such flag.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
)

if IS_SQLITE:
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
