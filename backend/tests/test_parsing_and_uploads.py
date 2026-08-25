"""
Parser robustness, duplicate detection, and upload validation.

Real LinkedIn exports vary wildly by locale, layout and export version, so the
parser is fed deliberately hostile text here: empty, enormous, non-Latin,
control characters, and dates that make no sense. It must always return a
usable dict rather than raise, and never report an impossible tenure.

Duplicate detection gets the case that actually loses data: two different
people whose names both failed to extract.
"""
from _harness import PDF_FILE, Results, client, make_user, restore_pdf_text, stub_pdf_text
import parser as P

r = Results()

HOSTILE_TEXT = {
    "empty": "",
    "whitespace only": "   \n\n\t  \n ",
    "single character": "x",
    "no line breaks": "a" * 5000,
    "only line breaks": "\n" * 1000,
    "null bytes": "Name\x00Here\nExperience\nCorp\n",
    "non-latin script": "Ł𝕬𝖓𝖉𝖗𝖊𝖜 Ｍｃ\nExperience\n株式会社テスト\n2020 - Present\n",
    "emoji": "🚀🚀🚀\nExperience\n🏢 Corp\n2019 - 2024\n",
    "right-to-left": "‮moc.elpmaxe\nExperience\nCorp\n",
    "enormous single line": "Experience\n" + ("Z" * 100000),
    "control characters": "".join(chr(i) for i in range(1, 32)) + "\nExperience\nCorp\n",
    "many overlapping ranges": "Experience\n" + "\n".join(f"20{i:02d} - 20{i + 1:02d}" for i in range(25)),
    "impossible future date": "Experience\nCorp\n2099 - Present\n",
    "backwards date range": "Experience\nCorp\n2025 - 2019\n",
    "markup injection": "<script>alert(1)</script>\nExperience\n<img src=x onerror=1>\n",
    "sql-shaped name": "Robert'); DROP TABLE connections;--\nExperience\nCorp\n",
}


def run():
    # ---- parser never raises, never reports impossible experience ----
    for label, text in HOSTILE_TEXT.items():
        try:
            data = P.extract_linkedin_profile_metadata(text)
            total = data.get("years_experience")
            current = data.get("current_company_years_experience")
            r.check(f"metadata parse survives: {label}", isinstance(data, dict) and "name" in data, "bad shape")
            r.check(f"total experience plausible: {label}", total is None or 0 <= total <= 35, f"got {total}")
            r.check(f"current tenure plausible: {label}", current is None or 0 <= current <= 25, f"got {current}")
        except Exception as exc:
            r.check(f"metadata parse survives: {label}", False, f"{type(exc).__name__}: {exc}")

        try:
            r.check(
                f"resume contact parse survives: {label}",
                isinstance(P.extract_resume_contact_info(text), dict),
                "bad shape",
            )
        except Exception as exc:
            r.check(f"resume contact parse survives: {label}", False, f"{type(exc).__name__}: {exc}")

    # ---- slug normalisation (documented to return "" when no /in/ slug exists) ----
    for raw, expected in [
        ("", ""),
        ("not a url", ""),
        ("https://linkedin.com/company/foo", ""),
        ("https://linkedin.com/in/abc", "abc"),
        ("https://www.linkedin.com/in/abc/", "abc"),
        ("http://in.linkedin.com/in/abc?trk=x", "abc"),
    ]:
        r.check(f"slug of {raw!r}", P.normalize_linkedin_slug(raw) == expected,
                f"got {P.normalize_linkedin_slug(raw)!r}")

    # ---- a sidebar full of skills must not become the person ----
    export = (
        "Contact\nwww.linkedin.com/in/dana-reed-8837 (LinkedIn)\n\n"
        "Top Skills\nData Storytelling\nBusiness Acumen\nKey Performance Indicators\n\n"
        "Languages\nEnglish\n\n"
        "Dana Reed\nSenior Data Analyst at Northwind\nChicago, Illinois, United States\n\n"
        "Summary\nAnalyst.\n\n"
        "Experience\nNorthwind\nSenior Data Analyst\nMarch 2021 - Present\nChicago, Illinois, United States\n"
    )
    parsed = P.extract_linkedin_profile_metadata(export)
    r.check("sidebar skill is not mistaken for the person", parsed["name"] == "Dana Reed", f"got {parsed['name']!r}")
    r.check("employer read from experience section", parsed["company"] == "Northwind", f"got {parsed['company']!r}")

    # ---- duplicate detection ----
    headers, _ = make_user("dedupe")

    stub_pdf_text("Unknown Candidate\nExperience\nAcme Corp\nEngineer\n2020 - Present\n")
    first = client.post("/api/connections/upload-profile", headers=headers, files=PDF_FILE).json()

    stub_pdf_text("Unknown Candidate\nExperience\nAcme Corp\nDesigner\n2018 - Present\n")
    second = client.post("/api/connections/upload-profile", headers=headers, files=PDF_FILE).json()

    r.check(
        "two unidentifiable people are kept apart",
        not (first.get("id") == second.get("id") and second.get("duplicate_detected")),
        "two different people were merged into one record",
    )

    stub_pdf_text(
        "Jane Roe\nEngineer at Foo\nExperience\nFoo\nEngineer\n2020 - Present\n"
        "https://www.linkedin.com/in/jane-roe-123/\n"
    )
    original = client.post("/api/connections/upload-profile", headers=headers, files=PDF_FILE).json()

    stub_pdf_text(
        "Jane Roe\nEngineer at Foo\nExperience\nFoo\nEngineer\n2020 - Present\n"
        "http://linkedin.com/in/jane-roe-123?trk=abc\n"
    )
    reupload = client.post("/api/connections/upload-profile", headers=headers, files=PDF_FILE).json()

    r.check(
        "same profile re-uploaded with a different url form is recognised",
        reupload.get("id") == original.get("id") and reupload.get("duplicate_detected"),
        f"original {original.get('id')} vs reupload {reupload.get('id')}",
    )
    restore_pdf_text()

    # ---- upload validation ----
    non_pdf = client.post(
        "/api/connections/upload-profile",
        headers=headers,
        files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    r.check("non-PDF upload refused", non_pdf.status_code == 400, f"status {non_pdf.status_code}")

    empty = client.post("/api/connections/upload-profile", headers=headers, data={"name": ""})
    r.check("upload with no content refused", empty.status_code >= 400, f"status {empty.status_code}")

    stub_pdf_text("Trav Test\nExperience\nCorp\n2020 - Present\n")
    traversal = client.post(
        "/api/connections/upload-profile",
        headers=headers,
        files={
            "file": ("ok.pdf", b"%PDF", "application/pdf"),
            "screenshot": ("../../../../evil.png", b"\x89PNG\r\n\x1a\n", "image/png"),
        },
    )
    restore_pdf_text()
    if traversal.status_code == 200:
        stored = traversal.json().get("screenshot_path") or ""
        r.check("directory traversal in a filename cannot escape uploads", ".." not in stored, f"stored at {stored}")
    else:
        r.check("screenshot upload handled", traversal.status_code < 500, f"status {traversal.status_code}")

    # ---- malformed request bodies ----
    for label, body, expected in [
        ("null name", {"name": None}, (400, 422)),
        ("missing name", {}, (400, 422)),
    ]:
        resp = client.post("/api/connections", headers=headers, json=body)
        r.check(f"connection create with {label} refused", resp.status_code in expected, f"status {resp.status_code}")

    oversized = client.post(
        "/api/settings/batch",
        headers=headers,
        json={"settings": [{"key": "tone_examples", "value": "x" * 200000}]},
    )
    r.check("very large setting value handled", oversized.status_code < 500, f"status {oversized.status_code}")

    null_value = client.post(
        "/api/settings/batch",
        headers=headers,
        json={"settings": [{"key": "tone_examples", "value": None}]},
    )
    r.check("null setting value handled", null_value.status_code < 500, f"status {null_value.status_code}")

    # ---- ids outside the database's integer range must not 500 ----
    for bad_id in (-1, 0, 999999999, 2 ** 63, 2 ** 70):
        for method, path in [
            ("GET", f"/api/connections/{bad_id}"),
            ("DELETE", f"/api/connections/{bad_id}"),
            ("PUT", f"/api/connections/{bad_id}/star"),
            ("DELETE", f"/api/keys/{bad_id}"),
        ]:
            try:
                resp = client.request(method, path, headers=headers)
                r.check(f"out-of-range id {method} {bad_id}", resp.status_code < 500, f"status {resp.status_code}")
            except Exception as exc:
                r.check(f"out-of-range id {method} {bad_id}", False, f"unhandled {type(exc).__name__}")

    return r.report("parsing, duplicate detection and uploads")


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
