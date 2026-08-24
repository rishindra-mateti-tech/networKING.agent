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


def _extract_company_from_experience(lines: list) -> str:
    """
    Pulls the current employer out of the Experience section. LinkedIn PDF
    exports order each entry as company, then role, then the date range, so
    the first usable line after the "Experience" heading is the employer.
    """
    for i, line in enumerate(lines):
        if line.strip().lower() != "experience":
            continue
        for candidate in lines[i + 1: i + 5]:
            c = candidate.strip()
            if not c:
                continue
            # Page furniture
            if re.match(r"^page\s+\d+\s+of\s+\d+$", c, re.IGNORECASE):
                continue
            # Tenure lines: "7 years 2 months", "1 year 11 months"
            if re.match(r"^\d+\s+(year|yr|month|mo)s?\b", c, re.IGNORECASE):
                continue
            # Date ranges: "September 2024 - Present", "2019 - 2021"
            if re.match(r"^(january|february|march|april|may|june|july|august|september|october|november|december)\b", c, re.IGNORECASE):
                continue
            if re.match(r"^\d{4}\s*[-–]", c):
                continue
            if c.startswith("("):
                continue
            # A location line ("United States", "Greater Seattle Area") can
            # end up first when an export's layout omits or repositions the
            # company line -- never return one of these as the employer.
            if _looks_like_location(c):
                continue
            # NOTE: deliberately not skipping every line that opens with a
            # digit. Real employers do ("10G Caterpillar - Aerotek", "3M",
            # "7-Eleven"), and a blanket digit rule silently demoted those to
            # the job title on the following line.
            if len(c) > 80:
                continue
            return c
    return None


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
        "connection_count": 500,  # Default
        "years_experience": 0.0,
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

    # ---- Heuristically calculate experience years ----
    # A raw sum of every "YYYY - YYYY" match over-counts: the same tenure often
    # appears twice (a summary blurb plus the full Experience entry), and
    # overlapping ranges (e.g. two promotions at one company, or concurrent
    # roles) would each add their own years on top of each other. Merging
    # intervals first, then summing only the merged (non-overlapping) spans,
    # gives a realistic total instead of an inflated one.
    #
    # LinkedIn's actual date format is "Month YYYY - Month YYYY" (e.g. "April
    # 2021 - June 2025"), not bare "YYYY - YYYY". A pattern that only allows
    # whitespace between the dash and the second year misses every completed
    # role outright, since a month name sits between them, undercounting
    # total experience down to just whatever "X - Present" range happens to
    # exist (or to nothing at all, if even that range spans under a year).
    year_ranges = re.findall(
        r"(\b20\d{2}\b)\s*[-\u2013\u2014]\s*(?:[A-Za-z]+\.?\s+)?(\b20\d{2}\b|Present)",
        pdf_text, re.IGNORECASE
    )
    current_year = datetime.date.today().year

    intervals = []
    for start, end in year_ranges:
        start_yr = int(start)
        end_yr = current_year if end.lower() == "present" else int(end)
        diff = end_yr - start_yr
        if 0 < diff < 20:  # Sanity filter
            intervals.append((start_yr, end_yr))

    total_years = 0.0
    if intervals:
        intervals.sort()
        merged = [intervals[0]]
        for start_yr, end_yr in intervals[1:]:
            last_start, last_end = merged[-1]
            if start_yr <= last_end:  # overlapping or duplicate, extend/merge
                merged[-1] = (last_start, max(last_end, end_yr))
            else:
                merged.append((start_yr, end_yr))
        total_years = sum(end_yr - start_yr for start_yr, end_yr in merged)

    if total_years > 0:
        metadata["years_experience"] = round(min(total_years, 35.0), 1)

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
