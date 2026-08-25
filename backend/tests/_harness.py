"""
Shared test harness.

Importing this module points the app at a throwaway SQLite file before any
application module loads, so running the suite can never read or write the
real database. Both database.py and migrate.py resolve their path from
DATABASE_URL, so setting it here is enough to isolate everything.

Deliberately dependency-free: the suite runs on the same interpreter that
runs the app, with no test framework to install.
"""
import atexit
import os
import sys
import tempfile
import uuid

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Must happen before importing database/migrate/main.
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="networking_test_"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"


@atexit.register
def _cleanup_tmp_db():
    for suffix in ("", "-wal", "-shm"):
        path = _TMP_DB + suffix
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

client = TestClient(main.app)


class Results:
    """Collects pass/fail so a whole file reports at once instead of stopping at the first failure."""

    def __init__(self):
        self.passed = []
        self.failed = []

    def check(self, name, condition, detail=""):
        if condition:
            self.passed.append(name)
        else:
            self.failed.append(f"{name} :: {detail}")

    def report(self, title):
        print(f"\n{title}")
        print(f"  passed: {len(self.passed)}  failed: {len(self.failed)}")
        for failure in self.failed:
            print(f"  [FAIL] {failure}")
        return len(self.failed) == 0


def make_user(prefix="user"):
    """Registers and logs in a fresh user, returning its auth header."""
    email = f"{prefix}_{uuid.uuid4().hex[:10]}@example.com"
    password = "testpass123"
    registered = client.post("/api/auth/register", json={"email": email, "password": password})
    assert registered.status_code == 200, registered.text
    logged_in = client.post("/api/auth/login", json={"email": email, "password": password})
    assert logged_in.status_code == 200, logged_in.text
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}, email


def stub_pdf_text(text):
    """
    Replaces PDF text extraction with fixed text, so upload behaviour can be
    exercised without carrying binary PDF fixtures in the repo.
    """
    main.parse_pdf_text = lambda _bytes: text


def restore_pdf_text():
    import parser as parser_module
    main.parse_pdf_text = parser_module.parse_pdf_text


PDF_FILE = {"file": ("profile.pdf", b"%PDF-1.4 stub", "application/pdf")}
