import io
import re
import datetime
from pypdf import PdfReader


def clean_unicode_text(text: str) -> str:
    """
    Normalizes unicode punctuation characters that cause encoding corruption
    on Windows systems. Converts curly quotes, smart apostrophes, em/en dashes,
    ellipsis, and other typographic characters to their ASCII equivalents.
    """
    if not text:
        return text

    replacements = {
        # Curly single quotes / apostrophes
        "\u2018": "'",   # LEFT SINGLE QUOTATION MARK
        "\u2019": "'",   # RIGHT SINGLE QUOTATION MARK (smart apostrophe)
        "\u201A": "'",   # SINGLE LOW-9 QUOTATION MARK
        "\u2039": "'",   # SINGLE LEFT-POINTING ANGLE QUOTATION MARK
        "\u203A": "'",   # SINGLE RIGHT-POINTING ANGLE QUOTATION MARK
        "\u0060": "'",   # GRAVE ACCENT (backtick used as quote)

        # Curly double quotes
        "\u201C": '"',   # LEFT DOUBLE QUOTATION MARK
        "\u201D": '"',   # RIGHT DOUBLE QUOTATION MARK
        "\u201E": '"',   # DOUBLE LOW-9 QUOTATION MARK
        "\u00AB": '"',   # LEFT-POINTING DOUBLE ANGLE QUOTATION MARK
        "\u00BB": '"',   # RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK

        # Dashes
        "\u2013": "-",   # EN DASH
        "\u2014": "-",   # EM DASH
        "\u2015": "-",   # HORIZONTAL BAR
        "\u2212": "-",   # MINUS SIGN

        # Ellipsis
        "\u2026": "...", # HORIZONTAL ELLIPSIS

        # Spaces
        "\u00A0": " ",   # NON-BREAKING SPACE
        "\u2002": " ",   # EN SPACE
        "\u2003": " ",   # EM SPACE
        "\u2009": " ",   # THIN SPACE
        "\u200B": "",    # ZERO WIDTH SPACE

        # Bullets and misc
        "\u2022": "-",   # BULLET
        "\u2023": ">",   # TRIANGULAR BULLET
        "\u25AA": "-",   # BLACK SMALL SQUARE
        "\u25CF": "-",   # BLACK CIRCLE (bullet)
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def normalize_linkedin_slug(url: str) -> str:
    """
    Reduces a LinkedIn profile URL to just its stable `/in/<slug>` identifier,
    lowercased, with no scheme, "www.", trailing slash, or query string. Two
    exports of the same profile taken months apart can differ in every one of
    those (http vs https, a `?miniProfileUrn=...` tracking param LinkedIn
    sometimes appends, a trailing slash), so comparing raw `profile_url`
    strings for equality would miss real duplicates. Returns "" when no
    `/in/<slug>` shape is found (e.g. a company page URL or empty input).
    """
    if not url:
        return ""
    match = re.search(r"linkedin\.com/in/([^/?#\s]+)", url, re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).strip().rstrip("/").lower()


def parse_pdf_text(file_bytes: bytes) -> str:
    """Extracts raw text from a PDF file using pypdf and normalizes unicode."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        full_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                full_text.append(text)
        raw = "\n".join(full_text)
        return clean_unicode_text(raw)
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {str(e)}")


_US_STATES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming",
]

_COUNTRIES = [
    "united states", "united states of america", "usa", "india", "canada",
    "united kingdom", "uk", "australia", "germany", "france", "singapore",
    "japan", "china", "brazil", "netherlands", "ireland", "israel",
    "south korea", "sweden", "spain", "italy", "mexico", "poland",
    "switzerland", "remote",
]


def _looks_like_location(text: str) -> bool:
    """
    True when a line reads as a place rather than an employer. LinkedIn puts
    the location immediately under the headline, exactly where a company name
    would otherwise sit, so this guard keeps "United States" from being stored
    as someone's employer.
    """
    if not text:
        return False
    lowered = text.strip().lower().rstrip(".")

    if lowered in _COUNTRIES or lowered in _US_STATES:
        return True
    if "area" in lowered or lowered.startswith("greater ") or "metro" in lowered:
        return True
    # "City, ST" / "City, Country" shapes
    if "," in lowered:
        parts = [p.strip() for p in lowered.split(",")]
        if any(p in _US_STATES or p in _COUNTRIES for p in parts):
            return True
        # Two-letter state abbreviation as the last part, e.g. "Austin, TX"
        if len(parts) >= 2 and len(parts[-1]) == 2 and parts[-1].isalpha():
            return True
    return False


_MONTH_TO_NUM = {}
for _idx, _full in enumerate(
    ["january", "february", "march", "april", "may", "june",
     "july", "august", "september", "october", "november", "december"],
    start=1,
):
    _MONTH_TO_NUM[_full] = _idx
    _MONTH_TO_NUM[_full[:3]] = _idx
_MONTH_TO_NUM["sept"] = 9

# One Experience entry's date line, in the shapes LinkedIn actually exports:
#     "March 2026 - Present (5 months)"
#     "May 2023 - July 2024 (1 year 3 months)"
#     "2019 - 2021"
# The trailing parenthesised duration is LinkedIn's own arithmetic, which is
# more trustworthy than anything derived here (it knows the exact export date),
# so it is captured and preferred when present.
_DATE_RANGE_LINE = re.compile(
    r"^(?:(?P<s_mon>[A-Za-z]{3,9})\.?\s+)?(?P<s_yr>(?:19|20)\d{2})"
    r"\s*[-–—]\s*"
    r"(?:(?:(?P<e_mon>[A-Za-z]{3,9})\.?\s+)?(?P<e_yr>(?:19|20)\d{2})"
    r"|(?P<present>present|current))"
    r"\s*(?:\((?P<dur>[^)]*)\))?\s*$",
    re.IGNORECASE,
)

# A bare tenure line. LinkedIn emits one of these directly under the company
# name when somebody held several roles at that one employer ("BeyondScroll" /
# "1 year 2 months" / then each role). It is a roll-up of the entries below it,
# so counting it as its own entry would double-count that whole employer.
_DURATION_ONLY_LINE = re.compile(
    r"^(?:(?P<yrs>\d+)\s*(?:years?|yrs?))?\s*(?:(?P<mos>\d+)\s*(?:months?|mos?))?$",
    re.IGNORECASE,
)

_PAGE_FURNITURE = re.compile(r"^page\s+\d+\s+of\s+\d+$", re.IGNORECASE)

# Headings that end the Experience section. Everything below one of these is a
# different part of the profile, and its date ranges are emphatically not work:
# a four-year degree under "Education" was silently inflating totals by four
# years, which is the single largest source of wrong experience numbers.
_SECTION_HEADINGS = {
    "education", "licenses & certifications", "licenses and certifications",
    "certifications", "skills", "top skills", "publications", "honors-awards",
    "honors & awards", "honors and awards", "awards", "volunteer experience",
    "volunteering", "languages", "interests", "recommendations", "courses",
    "projects", "organizations", "patents", "test scores", "summary",
    "contact", "accomplishments", "causes", "additional information",
    "certifications & licenses",
}


# How LinkedIn records working for yourself. It goes in the company slot like
# any employer, so it parses normally -- this only exists so the breakdown can
# label it honestly instead of presenting "Self-Employed" as a firm, and so
# these years are visibly counted rather than looking quietly dropped.
_SELF_EMPLOYED_RE = re.compile(
    # "Independent" only counts with one of the specific words after it, or
    # "Independent Bank" would be read as somebody working for themselves.
    r"^(self[\s\-]?employed|freelance(?:r|ing)?$|freelance\s|"
    r"independent\s+(?:consultant|contractor|contracting|professional|researcher)|"
    r"sole\s+proprietor(?:ship)?|own\s+business)\b",
    re.IGNORECASE,
)


def _is_self_employed(company: str) -> bool:
    """True when the 'employer' on an entry is the person working for themselves."""
    if not company:
        return False
    # "Self-Employed - Consulting" and "Freelance / Contract" both count
    head = re.split(r"[·|/,]", company)[0].strip()
    return bool(_SELF_EMPLOYED_RE.match(head))


def _parse_duration_text(text: str):
    """Reads "1 year 3 months" / "6 months" / "2 yrs" into a month count."""
    if not text:
        return None
    m = _DURATION_ONLY_LINE.match(text.strip())
    if not m or not (m.group("yrs") or m.group("mos")):
        return None
    return int(m.group("yrs") or 0) * 12 + int(m.group("mos") or 0)


# Company names that legitimately end in a period, so the "ends with a full
# stop means it is a sentence" rule below does not throw them away.
_CORPORATE_SUFFIX_RE = re.compile(
    r"\b(inc|corp|co|ltd|llc|l\.l\.c|plc|gmbh|ag|sa|nv|bv|pvt|pte|llp|s\.a|a\.s)\.$",
    re.IGNORECASE,
)


def _looks_like_prose(text: str) -> bool:
    """
    True for a responsibility bullet or its wrapped continuation, false for the
    short company/title lines that sit directly above a date range. Needed
    because a bullet's *last* line lands immediately above the next role's title
    when a person held two roles at one employer, and would otherwise be read as
    the employer -- one profile really did file a role under a company called
    "and performance monitoring across backend services."
    """
    if text.startswith(("-", ">", "*")):
        return True
    if len(text) > 70:
        return True
    # A trailing full stop marks a finished sentence. Employers essentially
    # never end in one unless it is a corporate suffix ("Acme Corp.").
    if text.endswith(".") and not _CORPORATE_SUFFIX_RE.search(text):
        return True
    # Achievement lines people paste into the description: "2017: Top Biller",
    # "2021 - promoted early". Real employers do start with a number ("3M",
    # "7-Eleven", "10G Caterpillar"), so this only rejects a four-digit year
    # used as a label.
    if re.match(r"^(?:19|20)\d{2}\s*[:.\)\-]", text):
        return True
    # A pipe is headline punctuation ("Recruiter | Ex-Google"), not part of a
    # company name.
    if "|" in text:
        return True
    # A bare year on its own line is a stray date, not an employer.
    if re.fullmatch(r"(?:19|20)\d{2}", text):
        return True
    # Fragments left behind when a long description wraps mid-sentence:
    # "$2M)", "development as per the requirement". A dollar figure or a
    # closing bracket with no opening one is never part of a company name.
    if "$" in text or (")" in text and "(" not in text):
        return True
    return False


def _experience_section_lines(lines: list) -> list:
    """The lines between the "Experience" heading and whatever heading ends it."""
    try:
        start = next(
            i for i, l in enumerate(lines) if l.strip().lower() == "experience"
        )
    except StopIteration:
        return []
    out = []
    for line in lines[start + 1:]:
        if line.strip().lower() in _SECTION_HEADINGS:
            break
        out.append(line)
    return out


def parse_experience_entries(lines: list) -> list:
    """
    Reads the Experience section into one record per role, with real month
    precision, so every number downstream can be shown its own working.

    A LinkedIn export lays each entry out as company, then title, then the date
    range, and repeats the title/date pair (without the company) for a second
    role at the same employer. Walking forwards and treating each date line as
    the terminator of an entry handles both shapes with one rule: the line just
    above a date range is the title, and the line above that is the company
    unless it is the employer-level tenure roll-up, in which case the company is
    one line higher again.
    """
    section = _experience_section_lines(lines)
    entries = []
    current_company = None
    pending = []  # candidate company/title lines seen since the last date line

    for raw in section:
        line = raw.strip()
        if not line or _PAGE_FURNITURE.match(line):
            continue

        date_match = _DATE_RANGE_LINE.match(line)
        if not date_match:
            if _looks_like_prose(line):
                # A bullet ends the header block; the employer still carries
                # over to any further roles listed under it.
                pending = []
            else:
                pending.append(line)
            continue

        title = pending[-1] if pending else None
        company = None
        if len(pending) >= 2:
            above = pending[-2]
            if _parse_duration_text(above) is not None:
                # Employer-level roll-up sits between company and first title
                above = pending[-3] if len(pending) >= 3 else None
            if above and not _looks_like_prose(above) and not _looks_like_location(above):
                company = above
            # Otherwise the employer is genuinely unknown for this entry. It is
            # deliberately left blank rather than inherited from the entry above:
            # LinkedIn lists roles newest first, so borrowing the previous
            # company would file an old job under a newer employer.
        elif len(pending) == 1:
            # One line between two date ranges is a second role at the same
            # employer, which LinkedIn writes without repeating the company.
            company = current_company
            if company is None:
                # Nothing established yet, so this lone line is the employer.
                company, title = title, None
        if company:
            current_company = company
        pending = []

        start_year = int(date_match.group("s_yr"))
        start_month = _MONTH_TO_NUM.get((date_match.group("s_mon") or "").lower())
        is_current = bool(date_match.group("present"))
        if is_current:
            today = datetime.date.today()
            end_year, end_month = today.year, today.month
        else:
            end_year = int(date_match.group("e_yr"))
            end_month = _MONTH_TO_NUM.get((date_match.group("e_mon") or "").lower())

        # Year-only ranges ("2019 - 2021") carry no month, so anchor both ends
        # at January rather than inventing a full extra year of tenure.
        s_abs = start_year * 12 + (start_month or 1)
        e_abs = end_year * 12 + (end_month or 1)
        if e_abs < s_abs or (e_abs - s_abs) > 12 * 60:
            continue

        linkedin_months = _parse_duration_text(date_match.group("dur"))
        derived_months = e_abs - s_abs + 1
        entries.append({
            "company": company,
            "title": title,
            "start_year": start_year,
            "start_month": start_month,
            "end_year": None if is_current else end_year,
            "end_month": None if is_current else end_month,
            "is_current": is_current,
            # LinkedIn computed its own duration at export time and knew the
            # exact export date; prefer it, and fall back to the dates.
            "months": linkedin_months if linkedin_months is not None else derived_months,
            "start_abs": s_abs,
            "end_abs": e_abs + 1,  # half-open, so back-to-back roles merge
        })
    return entries


def _merged_months(entries: list) -> int:
    """
    Distinct calendar time covered by these roles, overlaps counted once.

    Somebody holding three concurrent positions has not worked three times as
    long, and summing role durations is exactly how a student with a club
    officer post, a campus job and an internship ends up reading as a decade of
    experience.
    """
    spans = sorted((e["start_abs"], e["end_abs"]) for e in entries)
    if not spans:
        return 0
    merged = [list(spans[0])]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(end - start for start, end in merged)


def summarize_experience(lines: list) -> dict:
    """
    Turns the Experience section into the three numbers the UI shows, plus the
    per-role breakdown that justifies them. Returns zeroed values (and an empty
    breakdown) when the section is missing or unparseable, rather than guessing.
    """
    entries = parse_experience_entries(lines)
    if not entries:
        return {
            "years_experience": 0.0,
            "current_company": None,
            "current_company_years_experience": None,
            "total_role_months": 0,
            "distinct_months": 0,
            "breakdown": [],
        }

    distinct = _merged_months(entries)

    # The employer this person is filed under: the first current role listed.
    # LinkedIn shows current positions in the order the person chose, and the
    # one they put first is the one they lead with. Tenure is then measured
    # against that same employer -- including any earlier roles there, so a
    # promotion reads as continuous time rather than restarting the clock --
    # so the number and the company name on the card always agree.
    primary = next((e for e in entries if e["is_current"]), entries[0])
    same_employer = [
        e for e in entries
        if (e["company"] or "").strip().lower() == (primary["company"] or "").strip().lower()
    ] if primary["company"] else [primary]
    current_tenure = _merged_months(same_employer) if primary["is_current"] else None

    breakdown = [
        {
            "company": e["company"],
            "title": e["title"],
            "start": f"{e['start_year']:04d}-{e['start_month']:02d}" if e["start_month"] else str(e["start_year"]),
            "end": (
                None if e["is_current"]
                else (f"{e['end_year']:04d}-{e['end_month']:02d}" if e["end_month"] else str(e["end_year"]))
            ),
            "is_current": e["is_current"],
            "is_self_employed": _is_self_employed(e["company"]),
            "months": e["months"],
        }
        for e in entries
    ]

    return {
        "years_experience": round(min(distinct / 12, 60.0), 1),
        "current_company": primary["company"],
        "current_company_years_experience": (
            round(current_tenure / 12, 1) if current_tenure else None
        ),
        "total_role_months": sum(e["months"] for e in entries),
        "distinct_months": distinct,
        "breakdown": breakdown,
    }


def _extract_company_from_experience(lines: list) -> str:
    """
    The employer to file this person under, read out of the structured parse
    rather than off a fixed line offset -- which is what used to let a location
    line ("United States") become somebody's employer.
    """
    return summarize_experience(lines)["current_company"]


def _rejoin_wrapped_urls(pdf_text: str) -> str:
    """
    The narrow sidebar column wraps long values across a line break, which
    leaves URLs and emails truncated unless they are stitched back together:

        www.linkedin.com/in/mary-alexis-   +  jackson-3a8806186 (LinkedIn)
        www.linkedin.com/in/               +  sakthisankarraman (LinkedIn)
        gowthamisingam1998@gmail.co        +  m

    Runs before any other parsing so everything downstream sees whole values.
    """
    lines = pdf_text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        stripped = lines[i].rstrip()
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""

        # Profile URL split at a hyphen or at the trailing slash
        if (
            "linkedin.com/in/" in stripped.lower()
            and (stripped.endswith("-") or stripped.endswith("/"))
            and nxt
        ):
            # Only the first token continues the URL; a trailing "(LinkedIn)"
            # label is not part of it.
            out.append(stripped + nxt.split()[0])
            i += 2
            continue

        # Email split inside the domain, where the tail is a bare fragment
        if (
            "@" in stripped
            and not stripped.endswith(("com", "org", "net", "edu", "gov", "io"))
            and re.match(r"^[A-Za-z]{1,4}$", nxt)
        ):
            out.append(stripped + nxt)
            i += 2
            continue

        out.append(lines[i])
        i += 1
    return "\n".join(out)


# Words that mark a line as a job headline rather than a person's name.
_ROLE_WORDS = [
    # Roles
    "engineer", "engineering", "developer", "manager", "director", "analyst",
    "consultant", "specialist", "recruiter", "recruiting", "scientist",
    "designer", "architect", "founder", "co-founder", "cofounder", "intern",
    "associate", "officer", "president", "partner", "professional",
    "strategist", "swe", "author", "student", "advisor", "executive",
    "administrator", "coordinator", "supervisor", "technician", "researcher",
    "lead", "head", "owner", "coach", "trainer", "teacher", "professor",
    "attorney", "counsel", "accountant", "nurse", "physician",
    # Seniority modifiers
    "senior", "junior", "staff", "principal", "chief", "ceo", "cto", "coo",
    "cfo", "vp",
    # Functions
    "operations", "marketing", "sales", "product", "program", "project",
    "technical", "talent", "acquisition", "business", "finance", "support",
    "human resources",
    # Phrases that open a self-description rather than a name
    "helping", "building",
]


def _is_headline_like(text: str) -> bool:
    """
    True for a professional headline, false for a person's name. Every export
    reviewed puts one directly under the other, so this is the split that
    decides which line becomes the name.
    """
    if not text:
        return False
    lowered = text.lower()
    if len(text) > 45:
        return True
    if "|" in text or "@" in text:
        return True
    if re.search(r"\bat\b", lowered):
        return True
    return any(re.search(rf"\b{re.escape(w)}\b", lowered) for w in _ROLE_WORDS)


def _looks_like_person_name(text: str) -> bool:
    """Shape check for a name line: short, 1 to 5 mostly-alphabetic words."""
    if not text or len(text) > 45:
        return False
    if "@" in text or "linkedin.com" in text.lower() or "http" in text.lower():
        return False
    if _looks_like_location(text) or _is_headline_like(text):
        return False
    # Allow a credential suffix, e.g. "Seth Forbes, MBA" / "Micah Alsouss, SHRM-CP"
    core = text.split(",")[0].strip()
    words = core.split()
    if not (1 <= len(words) <= 5):
        return False
    if not core[:1].isupper():
        return False
    # Tolerate initials, periods, hyphens and parenthesised nicknames
    return all(re.match(r"^[A-Za-z.'()\-]+$", w) for w in words)


def extract_identity_block(lines: list) -> dict:
    """
    Locates the name, headline and location together, since their positions
    are only meaningful relative to each other.

    Every LinkedIn export follows the same order once the sidebar ends:
        <name> / <headline, sometimes wrapped over 2-3 lines> / <location>
    immediately above the first "Summary" or "Experience" heading. Anchoring
    on that heading and walking upwards is reliable in a way that counting
    lines from the top of the document is not, because the sidebar's length
    varies enormously (Contact, Top Skills, Languages, Certifications,
    Honors-Awards and Publications may each be present or absent).
    """
    result = {"name": None, "headline": None, "location": None}

    anchor = next(
        (i for i, l in enumerate(lines) if l.strip().lower() in ("summary", "experience")),
        None,
    )
    if anchor is None or anchor < 2:
        return result

    # The location always occupies the line directly above the heading.
    location_idx = anchor - 1
    if _looks_like_location(lines[location_idx]):
        result["location"] = lines[location_idx].strip()
        headline_end = location_idx - 1
    else:
        # No location on this profile; that slot is the tail of the headline.
        headline_end = location_idx

    # Walk up through the headline. A line belongs to it when it reads as a
    # headline, or when the line above it clearly wrapped (over 45 characters),
    # which makes this line that wrap's continuation.
    i = headline_end
    while i > 0:
        current = lines[i].strip()
        previous = lines[i - 1].strip()
        is_continuation = _is_headline_like(previous) and len(previous) > 45
        if _is_headline_like(current) or is_continuation:
            i -= 1
            continue
        break

    name_idx = i
    if 0 <= name_idx <= headline_end and _looks_like_person_name(lines[name_idx]):
        result["name"] = lines[name_idx].strip()
        if headline_end >= name_idx + 1:
            result["headline"] = " ".join(
                l.strip() for l in lines[name_idx + 1: headline_end + 1]
            ).strip()
    return result


def _name_from_profile_slug(lines: list, profile_url: str):
    """
    Matches a line against the profile URL slug, which LinkedIn derives from
    the person's name. This is far more dependable than guessing by position:
    many exports lead with a sidebar (Contact, Top Skills, Languages) whose
    entries look exactly like short names, which is how a profile ends up
    filed under a person called "English".
    """
    if not profile_url:
        return None
    match = re.search(r"/in/([^/?#\s]+)", profile_url)
    if not match:
        return None
    # Drop the trailing hash LinkedIn appends, keep the word-ish parts
    tokens = [t for t in re.split(r"[-_]", match.group(1).lower()) if t and not re.search(r"\d", t)]
    if not tokens:
        return None

    best, best_score = None, 0.0
    for line in lines[:40]:
        candidate = line.strip()
        if not candidate or len(candidate) > 60:
            continue
        if "@" in candidate or "linkedin.com" in candidate.lower():
            continue
        words = [w.lower().strip(".,()") for w in candidate.split()]
        if not words or len(words) > 6:
            continue
        matched = sum(1 for t in tokens if t in words)
        score = matched / len(tokens)
        if score > best_score:
            best, best_score = candidate, score
    # Require most of the slug to be accounted for before trusting it
    return best if best_score >= 0.6 else None


def _name_before_main_section(lines: list):
    """
    Walks back from the first main-content heading (Summary or Experience) to
    find the person's name. In every export the block reads name, headline,
    then location, immediately above that heading, so scanning backwards skips
    the sidebar entirely.
    """
    anchor = None
    for i, line in enumerate(lines):
        if line.strip().lower() in ("summary", "experience"):
            anchor = i
            break
    if anchor is None:
        return None

    for line in reversed(lines[max(0, anchor - 6): anchor]):
        candidate = line.strip()
        if not candidate or len(candidate) > 60:
            continue
        if "@" in candidate or "linkedin.com" in candidate.lower():
            continue
        if _looks_like_location(candidate):
            continue
        words = candidate.split()
        # Real names run 2 to 4 words. Job headlines are longer, which is what
        # separates "Mary Alexis Jackson" from the title sitting right below it.
        if not (2 <= len(words) <= 4):
            continue
        if not all(re.match(r"^[A-Za-z.\-']+$", w) for w in words):
            continue
        if not candidate[0].isupper():
            continue
        return candidate
    return None


def extract_linkedin_profile_metadata(pdf_text: str) -> dict:
    """
    Extracts basic candidate profile fields from LinkedIn 'Save to PDF' text.
    Uses multiple heuristic strategies to handle different LinkedIn PDF export formats:
      - Standard format: Name on line 1, headline on line 2
      - Contact-prefixed format: 'Contact' section appears early
      - Multi-line headline format: Title and company on separate lines
    """
    metadata = {
        "name": "Unknown Candidate",
        "current_title": None,
        "company": None,
        "location": None,
        "connection_count": None,  # Only set below if the PDF text actually states a count
        "years_experience": 0.0,
        "current_company_years_experience": None,
        "total_role_months": 0,
        "distinct_months": 0,
        "experience_breakdown": [],
        "profile_url": None,
        "email": None
    }

    # Must run before any URL matching, or a wrapped profile URL is captured
    # truncated at the line break.
    pdf_text = _rejoin_wrapped_urls(pdf_text)

    # Extract a contact email if the profile exposes one. LinkedIn PDF exports
    # put this in the Contact block near the top when the person has made it
    # visible. Skip linkedin.com addresses, those are never the person's email.
    email_matches = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', pdf_text)
    for candidate_email in email_matches:
        cleaned = candidate_email.strip().rstrip('.,;')
        if "linkedin.com" not in cleaned.lower():
            metadata["email"] = cleaned
            break

    # Extract LinkedIn URL if present in PDF
    linkedin_url_match = re.search(
        r'(https?://[a-z0-9\-]+\.linkedin\.com/in/[^\s\n]+|linkedin\.com/in/[^\s\n]+)',
        pdf_text,
        re.IGNORECASE
    )
    if linkedin_url_match:
        url = linkedin_url_match.group(1).strip()
        url = re.sub(r'[\)\.\,\;\>]+$', '', url)
        if not url.startswith('http'):
            url = 'https://' + url
        metadata["profile_url"] = url

    lines = [line.strip() for line in pdf_text.split("\n") if line.strip()]
    if not lines:
        return metadata

    # --- Section header keywords that should NOT be treated as names ---
    section_keywords = [
        "contact", "experience", "education", "skills", "summary",
        "about", "licenses", "certifications", "publications",
        "honors", "awards", "projects", "languages", "interests",
        "recommendations", "top skills", "page", "linkedin.com",
        "volunteer", "organizations", "courses"
    ]

    def is_section_header(text: str) -> bool:
        lowered = text.lower()
        return any(kw in lowered for kw in section_keywords)

    def looks_like_name(text: str) -> bool:
        """
        A name candidate should be:
        - Short (under 60 chars)
        - Not a section header
        - Not an email address or URL
        - Consists mostly of alphabetic words (2-4 words typical)
        """
        if len(text) > 60:
            return False
        if is_section_header(text):
            return False
        if "@" in text or "http" in text.lower() or "linkedin.com" in text.lower():
            return False
        # Check if it looks like a human name: 2-5 words, mostly alpha
        words = text.split()
        if len(words) < 1 or len(words) > 6:
            return False
        alpha_words = sum(1 for w in words if re.match(r"^[A-Za-z\.\-']+$", w))
        return alpha_words >= len(words) * 0.7

    # ---- Name, headline and location ----
    # Resolved together by anchoring on the first "Summary"/"Experience"
    # heading and reading upwards. See extract_identity_block.
    identity = extract_identity_block(lines)
    name_line_idx = 0

    if identity["name"]:
        metadata["name"] = identity["name"]
        name_line_idx = lines.index(identity["name"]) if identity["name"] in lines else 0
        if identity["headline"]:
            metadata["current_title"] = identity["headline"]
        if identity["location"]:
            metadata["location"] = identity["location"]
    else:
        # Fallbacks for exports that carry no Summary/Experience heading at all.
        slug_name = _name_from_profile_slug(lines, metadata["profile_url"])
        if slug_name and slug_name in lines:
            metadata["name"] = slug_name
            name_line_idx = lines.index(slug_name)
        else:
            for i, line in enumerate(lines[:8]):
                if _looks_like_person_name(line) and not is_section_header(line):
                    metadata["name"] = line
                    name_line_idx = i
                    break
        # Best-effort headline from the line right below whatever name we found
        if not metadata["current_title"] and name_line_idx + 1 < len(lines):
            candidate = lines[name_line_idx + 1]
            if not is_section_header(candidate) and "@" not in candidate:
                metadata["current_title"] = candidate

    # ---- Company ----
    # Ordered by how trustworthy the source is:
    #   1. An explicit "at <Company>" inside the headline.
    #   2. The Experience section, where each entry runs company, role, dates.
    #      This is the dependable one, because plenty of headlines are a bare
    #      job title with no employer named in them at all.
    title_text = metadata["current_title"] or ""
    company_match = re.search(r"at\s+([^|@]+)$", title_text, re.IGNORECASE)
    if company_match:
        metadata["company"] = company_match.group(1).strip()
    else:
        experience_company = _extract_company_from_experience(lines)
        if experience_company:
            metadata["company"] = experience_company

    # ---- Extract connection count ----
    conn_match = re.search(r"(\d+)\+?\s*connections?", pdf_text, re.IGNORECASE)
    if conn_match:
        metadata["connection_count"] = int(conn_match.group(1))

    # ---- Experience ----
    # Read only the Experience section, one record per role, at month
    # precision. Two things this deliberately does not do, because both
    # produced badly wrong numbers:
    #   - scan the whole document. A "(2020 - 2024)" degree under Education is
    #     not four years of work, and neither is a certification year.
    #   - sum role durations. Concurrent roles (a campus job, a club officer
    #     post and an internship held at once) each contributed their own full
    #     span, so overlapping time was counted two and three times over.
    # See summarize_experience: overlapping spans are merged before totalling,
    # and the per-role breakdown is carried through so the UI can show the
    # difference between time worked and roles held.
    experience = summarize_experience(lines)
    metadata["years_experience"] = experience["years_experience"]
    metadata["current_company_years_experience"] = experience["current_company_years_experience"]
    metadata["total_role_months"] = experience["total_role_months"]
    metadata["distinct_months"] = experience["distinct_months"]
    metadata["experience_breakdown"] = experience["breakdown"]

    return metadata


def extract_resume_contact_info(resume_text: str) -> dict:
    """
    Best-effort structured extraction (LinkedIn/GitHub/portfolio URLs, email,
    phone, location) from résumé text, so the TwinAgent profile can auto-fill
    the Social Links card instead of leaving the user to retype what's
    already on their own resume. Reuses the same building blocks as
    extract_linkedin_profile_metadata: URLs wrap across a line break in a PDF
    export the same way regardless of whether the source is a LinkedIn
    profile or a resume, so _rejoin_wrapped_urls runs first here too.
    """
    result = {
        "github_url": None,
        "portfolio_url": None,
        "linkedin_url": None,
        "email": None,
        "phone": None,
        "location": None,
        "full_name": None,
    }
    if not resume_text:
        return result

    text = _rejoin_wrapped_urls(resume_text)

    email_matches = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
    if email_matches:
        result["email"] = email_matches[0].strip().rstrip('.,;')

    linkedin_match = re.search(
        r'(https?://[a-z0-9\-]+\.linkedin\.com/in/[^\s\n]+|linkedin\.com/in/[^\s\n]+)',
        text, re.IGNORECASE
    )
    if linkedin_match:
        url = re.sub(r'[\)\.\,\;\>]+$', '', linkedin_match.group(1).strip())
        result["linkedin_url"] = url if url.startswith("http") else "https://" + url

    github_match = re.search(
        r'(https?://)?(www\.)?github\.com/[A-Za-z0-9_-]+', text, re.IGNORECASE
    )
    if github_match:
        url = re.sub(r'[\)\.\,\;\>]+$', '', github_match.group(0).strip())
        result["github_url"] = url if url.startswith("http") else "https://" + url

    # Portfolio detection is the riskiest of these: resumes commonly list
    # several project demo links (often on free hosts like vercel.app or
    # netlify.app, exactly the same shape as a real portfolio link), and
    # grabbing "the first URL that isn't LinkedIn/GitHub" would just as
    # happily grab a project's deployment link as the person's actual site.
    # So this is deliberately conservative: only trust a URL that either (a)
    # sits next to an explicit "portfolio"/"website" label, or (b) appears in
    # the header/contact block before any section heading, which is where a
    # resume's own site link normally lives alongside the email and phone.
    # Anything inside a "Projects" section is excluded outright. If neither
    # signal is found, portfolio_url stays None rather than guessing.
    section_headings = {
        "experience", "work experience", "professional experience",
        "education", "projects", "personal projects", "project experience",
        "skills", "technical skills", "summary", "about", "certifications",
        "publications", "awards", "honors", "volunteer", "interests",
        "languages", "references", "contact",
    }
    portfolio_keyword_re = re.compile(r'\b(portfolio|personal (?:site|website)|my website|website)\b', re.IGNORECASE)
    portfolio_tlds = r"(?:dev|io|me|app|xyz|tech|page|site|design|studio|works|codes|vercel\.app|netlify\.app|github\.io|pages\.dev)"
    bare_domain_re = re.compile(rf'\b([a-zA-Z0-9](?:[a-zA-Z0-9-]{{0,61}}[a-zA-Z0-9])?\.{portfolio_tlds})(/[^\s]*)?\b')

    lines_raw = text.split("\n")

    def _is_heading(line: str) -> bool:
        return line.strip().lower().rstrip(":") in section_headings

    projects_start, projects_end = None, len(lines_raw)
    for i, line in enumerate(lines_raw):
        stripped = line.strip().lower().rstrip(":")
        if stripped in ("projects", "personal projects", "project experience"):
            projects_start = i
        elif projects_start is not None and i > projects_start and _is_heading(line):
            projects_end = i
            break

    first_heading_idx = next((i for i, l in enumerate(lines_raw) if _is_heading(l)), len(lines_raw))

    candidates = []  # (priority, url) -- lower priority number wins
    for i, line in enumerate(lines_raw):
        if projects_start is not None and projects_start <= i < projects_end:
            continue  # inside "Projects": these are demo links, not the portfolio

        found = [m.group(0) for m in re.finditer(r'https?://[^\s\n]+', line, re.IGNORECASE)]
        for m in bare_domain_re.finditer(line):
            if m.start() > 0 and line[m.start() - 1] == "@":
                continue  # part of an email, not a bare domain
            found.append(m.group(0))

        for raw_url in found:
            url = re.sub(r'[\)\.\,\;\>]+$', '', raw_url.strip())
            lowered = url.lower()
            if "linkedin.com" in lowered or "github.com" in lowered:
                continue
            full_url = url if url.startswith("http") else "https://" + url
            has_keyword = bool(
                portfolio_keyword_re.search(line)
                or (i > 0 and portfolio_keyword_re.search(lines_raw[i - 1]))
            )
            if has_keyword:
                candidates.append((0, full_url))
            elif i <= first_heading_idx:
                candidates.append((1, full_url))
            # else: body text with no header/keyword signal -- too risky to trust

    if candidates:
        candidates.sort(key=lambda c: c[0])
        result["portfolio_url"] = candidates[0][1]

    phone_match = re.search(
        r'(\+\d{1,2}[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b', text
    )
    if phone_match:
        result["phone"] = phone_match.group(0).strip()

    # Location: best-effort scan of the header area (first ~10 non-empty
    # lines), where a resume's city/state line typically sits near the name.
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for line in lines[:10]:
        if _looks_like_location(line):
            result["location"] = line
            break

    # Full name: almost always the very first substantial line of a resume.
    # Reuses the same name-shape heuristic already trusted for LinkedIn PDFs.
    for line in lines[:5]:
        if _looks_like_person_name(line):
            result["full_name"] = line
            break

    return result
