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

    # ---- experience is read off the Experience section, at month precision ----
    # Regression cases from two real exports. Both used to report exactly 5.0
    # years: the old parser summed every "YYYY - YYYY" in the whole document,
    # so a four-year degree under Education counted as four years of work.
    CONCURRENT_STUDENT = """Lohitha Donuri
Computer Science Graduate Student
United States
Experience
graduate studies wright state university
Graduate student advisory board
April 2026 - Present (6 months)
Entrepreneurship Club at Wright State
outreach chair
January 2026 - Present (9 months)
United States
Page 1 of 3
Wright State University
Event Support Coordinator - Nutter Center
November 2025 - Present (11 months)
United States
ss steels
Software Engineer
May 2023 - July 2024 (1 year 3 months)
Hyderabad
Improved operational efficiency by approximately 15% across several locations
through cross functional program coordination.
Swayam ED-cell,Vasavi College Of Engineering
Student Volunteer
May 2021 - June 2024 (3 years 2 months)
Hyderabad
viclipy
Founder
January 2021 - June 2024 (3 years 6 months)
Hyderabad
Education
Wright State University
Master's degree, Computer Science (January 2025 - December 2026)
Vasavi College of Engg
Bachelor of Engineering - BE, Information Technology (2020 - 2024)
"""

    PROMOTED_AT_ONE_EMPLOYER = """Rishindra Mateti
AI Engineer Intern
Dallas-Fort Worth Metroplex
Experience
ZUZU
AI Engineer Intern
March 2026 - Present (5 months)
- Build an AI-powered student onboarding platform.
Wright State University
Student Technology Support Analyst
November 2025 - Present (9 months)
United States
- Support event-day technology and operations at the Nutter Center.
BeyondScroll
1 year 2 months
Junior Software Engineer
March 2024 - August 2024 (6 months)
Hyderabad
- Contributed to data synchronization, exception handling, functional testing,
and performance monitoring across backend services.
Backend Engineering Intern
July 2023 - February 2024 (8 months)
Hyderabad
Education
INSTITUTE OF AERONAUTICAL ENGINEERING
Bachelor of Technology - BTech, Computer Science and
Engineering (2020 - 2024)
"""

    lohitha = P.extract_linkedin_profile_metadata(CONCURRENT_STUDENT)
    r.check(
        "education years are not counted as work experience",
        lohitha["years_experience"] == 4.5,
        f"expected 4.5, got {lohitha['years_experience']}",
    )
    r.check(
        "concurrent roles are merged, not summed",
        lohitha["years_experience"] < lohitha["total_role_months"] / 12,
        "overlapping roles were summed",
    )
    r.check(
        "every role appears in the breakdown",
        len(lohitha["experience_breakdown"]) == 6,
        f"got {len(lohitha['experience_breakdown'])} entries",
    )
    r.check(
        "all three concurrent roles are flagged current",
        sum(1 for e in lohitha["experience_breakdown"] if e["is_current"]) == 3,
        "wrong current-role count",
    )
    r.check(
        "sub-year tenure is measured, not defaulted",
        lohitha["current_company_years_experience"] == 0.5,
        f"got {lohitha['current_company_years_experience']}",
    )

    rishindra = P.extract_linkedin_profile_metadata(PROMOTED_AT_ONE_EMPLOYER)
    r.check(
        "months are counted, not just whole years",
        rishindra["years_experience"] == 2.1,
        f"expected 2.1, got {rishindra['years_experience']}",
    )
    r.check(
        "company is the first current role, not a location",
        rishindra["company"] == "ZUZU",
        f"got {rishindra['company']}",
    )
    r.check(
        "a second role under one employer keeps that employer",
        [e["company"] for e in rishindra["experience_breakdown"]].count("BeyondScroll") == 2,
        "a bullet line was read as the employer",
    )
    r.check(
        "employer-level tenure roll-up is not its own entry",
        len(rishindra["experience_breakdown"]) == 4,
        f"got {len(rishindra['experience_breakdown'])} entries",
    )

    SELF_EMPLOYED = """Jordan Rivera
Consultant
Experience
Self-Employed
Independent Data Consultant
January 2019 - Present (7 years 8 months)
Remote
Education
Some University
BS (2014 - 2018)
"""
    self_emp = P.extract_linkedin_profile_metadata(SELF_EMPLOYED)
    r.check(
        "self-employment counts as experience",
        self_emp["years_experience"] > 7,
        f"got {self_emp['years_experience']}",
    )
    r.check(
        "self-employment is labelled as such",
        self_emp["experience_breakdown"][0]["is_self_employed"] is True,
        "not flagged",
    )
    r.check(
        "a real employer is not mistaken for self-employment",
        P._is_self_employed("Independent Bank Group") is False,
        "false positive",
    )

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
