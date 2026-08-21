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


def run_migrations():
    database_url = os.getenv("DATABASE_URL", "")
    if database_url.startswith("postgres"):
        # A fresh Postgres database gets the full current schema straight from
        # the SQLAlchemy models (see Base.metadata.create_all in main.py) --
        # the column-by-column ALTER TABLE dance below only exists to patch up
        # SQLite files created before certain columns/encryption existed.
        print("[MIGRATE] Postgres detected, skipping SQLite-specific column backfill.")
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
    ]

    
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

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='api_keys'")
    if cursor.fetchone():
        _encrypt_existing_api_keys(cursor)
        conn.commit()

    conn.close()
    print("Database migrations checked/completed successfully.")

if __name__ == "__main__":
    run_migrations()
