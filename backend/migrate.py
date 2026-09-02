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


def _reparse_stored_profiles(cursor, placeholder="?"):
    """
    Re-reads the saved PDF text of every profile that predates the current
    parser and rewrites the fields derived from it.

    Parser fixes have never reached rows already in the database: a profile
    parsed months ago keeps whatever the parser of the day produced, forever,
    because nothing re-reads profile_text unless the same PDF is uploaded
    again. Six real profiles were filed under "Unknown Candidate" or under a
    line lifted from the sidebar's skills list ("Data Storytelling", "Team
    Building"), with employers to match, long after the name extraction that
    got them wrong had been fixed.

    Only rows that still carry raw profile text are touched, and only fields
    that come from parsing it. A blank experience_breakdown is the marker for
    "not yet reparsed", so an empty list is written when a profile genuinely
    has no readable Experience section and the same rows are not re-examined
    on every boot. Manually created connections have no profile_text and are
    left alone entirely.
    """
    import json
    from parser import extract_linkedin_profile_metadata, summarize_experience

    cursor.execute(
        "SELECT id, profile_text, name, current_title, company, company_locked, "
        "location, candidate_email, profile_url FROM connections "
        "WHERE experience_breakdown IS NULL AND profile_text IS NOT NULL"
    )
    rows = cursor.fetchall()
    if not rows:
        return

    updated = 0
    renamed = 0
    for (conn_id, profile_text, name, title, company, company_locked,
         location, email, profile_url) in rows:
        try:
            lines = [l.strip() for l in (profile_text or "").split("\n") if l.strip()]
            summary = summarize_experience(lines)
            fresh = extract_linkedin_profile_metadata(profile_text)
        except Exception as e:
            print(f"[MIGRATE] Could not reparse connection {conn_id}: {e}")
            continue

        # Each of these is only overwritten when the fresh parse actually found
        # something, so a re-read that comes up empty never blanks a field that
        # already has a usable value.
        fresh_name = fresh.get("name")
        if fresh_name and fresh_name != "Unknown Candidate" and fresh_name != name:
            print(f"[MIGRATE] Connection {conn_id}: name {name!r} -> {fresh_name!r}")
            name = fresh_name
            renamed += 1
        # company_locked marks a company the user chose themselves, which
        # outranks anything re-read from the PDF.
        if summary["current_company"] and not company_locked:
            company = summary["current_company"]
        title = fresh.get("current_title") or title
        location = fresh.get("location") or location
        email = fresh.get("email") or email
        profile_url = fresh.get("profile_url") or profile_url

        cursor.execute(
            f"UPDATE connections SET experience_breakdown = {placeholder}, "
            f"years_experience = {placeholder}, "
            f"current_company_years_experience = {placeholder}, "
            f"name = {placeholder}, current_title = {placeholder}, "
            f"company = {placeholder}, location = {placeholder}, "
            f"candidate_email = {placeholder}, profile_url = {placeholder} "
            f"WHERE id = {placeholder}",
            (
                json.dumps(summary["breakdown"]),
                summary["years_experience"],
                summary["current_company_years_experience"],
                name, title, company, location, email, profile_url,
                conn_id,
            ),
        )
        updated += 1
    print(
        f"[MIGRATE] Reparsed {updated} stored profile(s) with the current parser"
        f"{f', correcting {renamed} name(s)' if renamed else ''}."
    )


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
    ("posts_screenshot_path", "TEXT", "TEXT"),
    ("company_locked", "BOOLEAN", "BOOLEAN"),
    ("experience_breakdown", "TEXT", "TEXT"),
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
        _reparse_stored_profiles(cursor, placeholder="%s")
        conn.commit()
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

    _reparse_stored_profiles(cursor)
    conn.commit()

    conn.close()
    print("Database migrations checked/completed successfully.")

if __name__ == "__main__":
    run_migrations()
