import sqlite3
import os

from crypto import encrypt_value, is_encrypted


def _encrypt_existing_api_keys(cursor):
    """
    One-time backfill: any api_keys.key_value written before encryption-at-rest was
    added is still plaintext. Encrypt it in place (raw SQL, bypassing the ORM so we
    don't double-encrypt values the ORM's EncryptedString type would otherwise re-wrap).
    """
    cursor.execute("SELECT id, key_value FROM api_keys")
    rows = cursor.fetchall()
    for key_id, key_value in rows:
        if key_value and not is_encrypted(key_value):
            cursor.execute(
                "UPDATE api_keys SET key_value = ? WHERE id = ?",
                (encrypt_value(key_value), key_id)
            )
            print(f"[MIGRATE] Encrypted plaintext API key id={key_id} at rest.")


def _resolve_db_path() -> str:
    """Mirrors database.py's DATABASE_URL resolution so migrations hit the same file."""
    database_url = os.getenv("DATABASE_URL", "")
    if database_url.startswith("sqlite:///"):
        raw_path = database_url[len("sqlite:///"):]
        if raw_path.startswith("./"):
            return os.path.join(os.path.dirname(__file__), raw_path[2:])
        return raw_path
    return os.path.join(os.path.dirname(__file__), "networking.db")


# Columns added to `connections` after the table already existed in production.
# Base.metadata.create_all only creates missing TABLES, not missing columns on
# existing tables, so both SQLite and Postgres need this list kept up to date
# whenever a new Column is added to models.py after initial release.
_NEW_CONNECTION_COLUMNS = [
    ("sent_at", "DATETIME", "TIMESTAMP"),
    ("replied_at", "DATETIME", "TIMESTAMP"),
    ("conversation_verdict", "TEXT", "TEXT"),
    ("conversation_verdict_reason", "TEXT", "TEXT"),
    ("conversation_recommended_action", "TEXT", "TEXT"),
    ("pdf_filename", "TEXT", "TEXT"),
    ("candidate_email", "TEXT", "TEXT"),
    ("generated_email_subject", "TEXT", "TEXT"),
    ("generated_email_body", "TEXT", "TEXT"),
    ("current_company_years_experience", "REAL", "DOUBLE PRECISION"),
]
_NEW_INTERACTION_LOG_COLUMNS = [
    ("screenshot_path", "TEXT", "TEXT"),
]


def _run_postgres_migrations(database_url: str):
    import psycopg2

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()
    try:
        for col_name, _sqlite_type, pg_type in _NEW_CONNECTION_COLUMNS:
            cursor.execute(f"ALTER TABLE connections ADD COLUMN IF NOT EXISTS {col_name} {pg_type}")
        for col_name, _sqlite_type, pg_type in _NEW_INTERACTION_LOG_COLUMNS:
            cursor.execute(f"ALTER TABLE interaction_logs ADD COLUMN IF NOT EXISTS {col_name} {pg_type}")
        conn.commit()
        print("[MIGRATE] Postgres: verified/added new columns on connections and interaction_logs.")
    except Exception as e:
        print(f"[MIGRATE] Postgres migration error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def run_migrations():
    database_url = os.getenv("DATABASE_URL", "")
    if database_url.startswith("postgres"):
        _run_postgres_migrations(database_url)
        return

    db_path = _resolve_db_path()
    print(f"Running database migrations on: {db_path}")

    if not os.path.exists(db_path):
        print("Database file does not exist yet. It will be initialized by SQLAlchemy.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get existing columns
    cursor.execute("PRAGMA table_info(connections)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    
    # Target columns to add
    new_columns = [
        ("networking_score", "REAL"),
        ("reply_probability", "REAL"),
        ("hiring_probability_score", "TEXT"),
        ("is_decision_maker", "TEXT"),
        ("referral_potential", "TEXT"),
        ("networking_difficulty", "TEXT"),
        ("conversation_starter", "TEXT"),
        ("avoid_points", "TEXT"),
        ("best_message_type", "TEXT"),
        ("generated_outreach_referral", "TEXT"),
        ("generated_outreach_coffee", "TEXT"),
        ("generated_outreach_technical", "TEXT"),
        ("generated_outreach_relationship", "TEXT"),
        ("generated_outreach_featured", "TEXT"),
        ("hiring_badge_status", "TEXT")
    ] + [(name, sqlite_type) for name, sqlite_type, _pg_type in _NEW_CONNECTION_COLUMNS]


    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            print(f"Adding column '{col_name}' ({col_type}) to connections table...")
            try:
                cursor.execute(f"ALTER TABLE connections ADD COLUMN {col_name} {col_type}")
                conn.commit()
            except Exception as e:
                print(f"Error adding column '{col_name}': {e}")
        else:
            print(f"Column '{col_name}' already exists.")

    cursor.execute("PRAGMA table_info(interaction_logs)")
    existing_log_columns = [row[1] for row in cursor.fetchall()]
    for col_name, sqlite_type, _pg_type in _NEW_INTERACTION_LOG_COLUMNS:
        if col_name not in existing_log_columns:
            print(f"Adding column '{col_name}' ({sqlite_type}) to interaction_logs table...")
            try:
                cursor.execute(f"ALTER TABLE interaction_logs ADD COLUMN {col_name} {sqlite_type}")
                conn.commit()
            except Exception as e:
                print(f"Error adding column '{col_name}': {e}")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='api_keys'")
    if cursor.fetchone():
        _encrypt_existing_api_keys(cursor)
        conn.commit()

    conn.close()
    print("Database migrations checked/completed successfully.")

if __name__ == "__main__":
    run_migrations()
