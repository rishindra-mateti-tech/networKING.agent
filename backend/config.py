import os
import secrets

from dotenv import load_dotenv, set_key

_ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")

# Load whatever is already on disk first.
load_dotenv(_ENV_PATH)


def _get_or_create_secret(key: str) -> str:
    """
    Returns the value of an env var, generating and persisting a fresh
    cryptographically-random one into backend/.env the first time the app
    boots without it configured. This avoids ever shipping a real secret
    in source control while still working out of the box for a fresh clone.
    """
    value = os.getenv(key)
    if value:
        return value

    value = secrets.token_hex(32)
    if not os.path.exists(_ENV_PATH):
        open(_ENV_PATH, "a").close()
    set_key(_ENV_PATH, key, value)
    os.environ[key] = value
    print(f"[CONFIG] Generated a new {key} and saved it to backend/.env")
    return value


JWT_SECRET_KEY = _get_or_create_secret("JWT_SECRET_KEY")
ENCRYPTION_KEY = _get_or_create_secret("ENCRYPTION_KEY")

# From Google Cloud Console -> APIs & Services -> Credentials -> OAuth client ID
# (type "Web application"). Not auto-generated: you create this yourself.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

# Comma-separated list of allowed frontend origins, e.g.
# "http://localhost:3000,https://app.example.com"
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
