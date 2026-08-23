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
            # Page furniture and date lines are not company names
            if re.match(r"^page\s+\d+\s+of\s+\d+$", c, re.IGNORECASE):
                continue
            if re.match(r"^[\d(]", c):
                continue
            if re.match(r"^(january|february|march|april|may|june|july|august|september|october|november|december)\b", c, re.IGNORECASE):
                continue
            if len(c) > 80:
                continue
            return c
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

    # ---- Strategy 1: First non-header line is the name ----
    name_found = False
    name_line_idx = 0
    for i, line in enumerate(lines[:5]):
        if looks_like_name(line):
            metadata["name"] = line
            name_line_idx = i
            name_found = True
            break

    # ---- Strategy 2: If "Contact" appears in line 2-4, name is likely line before it ----
    if not name_found:
        for i, line in enumerate(lines[:6]):
            if "contact" in line.lower() and i > 0:
                candidate = lines[i - 1]
                if looks_like_name(candidate):
                    metadata["name"] = candidate
                    name_line_idx = i - 1
                    name_found = True
                    break

    # ---- Extract headline/title and company ----
    # Look at lines after the name, before the first section header
    headline_lines = []
    for line in lines[name_line_idx + 1: name_line_idx + 8]:
        # NOTE: the skip checks below must run BEFORE the section-header break.
        # A profile URL line contains "linkedin.com", which is also a
        # section-header keyword, so testing for the header first would abort
        # the whole scan on the contact block and never reach the real headline
        # sitting one line further down.

        # Skip lines that look like URLs or email addresses
        if "@" in line or "linkedin.com" in line.lower() or line.lower().startswith("www."):
            continue
        # Skip lines that are just numbers (connection counts, etc.)
        if re.match(r"^\d+\s*(connections?|followers?)?$", line, re.IGNORECASE):
            continue
        # Skip phone numbers. LinkedIn's Contact block lists these right under
        # the name, and without this they get mistaken for the job headline
        # (e.g. a card showing "+1213... (Mobile)" where the title should be).
        if re.search(r'(\+?\d[\d\s().-]{7,}\d)', line):
            continue
        if re.search(r'\b(mobile|phone|tel|cell)\b', line, re.IGNORECASE):
            continue

        # A genuine section header (Experience, Education, ...) means the
        # headline block is over.
        if is_section_header(line):
            break

        headline_lines.append(line)

    if headline_lines:
        metadata["current_title"] = headline_lines[0]

        # Company, in order of how trustworthy the source is:
        #
        # 1. An explicit "at <Company>" inside the headline.
        # 2. The Experience section. LinkedIn exports list the company name
        #    first, then the role, then the dates, so the line right after
        #    the "Experience" heading is the current employer. This is the
        #    reliable one: plenty of headlines are just a job title with no
        #    company in them at all.
        # 3. The second headline line, but only when it isn't obviously a
        #    location. LinkedIn puts the person's location directly under
        #    the headline, which is how a profile ends up filed under a
        #    company called "United States".
        company_match = re.search(r"\bat\s+(.+)$", headline_lines[0], re.IGNORECASE)
        if company_match:
            metadata["company"] = company_match.group(1).strip()
        else:
            experience_company = _extract_company_from_experience(lines)
            if experience_company:
                metadata["company"] = experience_company
            elif len(headline_lines) > 1:
                potential_company = headline_lines[1]
                if len(potential_company) < 80 and not _looks_like_location(potential_company):
                    metadata["company"] = potential_company

    # ---- Extract location ----
    # Reuses the same shared helper the company fallback uses, so a line is
    # never treated as a location in one place and an employer in another.
    for line in lines[name_line_idx + 1: name_line_idx + 10]:
        if is_section_header(line):
            continue
        if "@" in line or "linkedin.com" in line.lower():
            continue
        if _looks_like_location(line):
            metadata["location"] = line
            break

    # ---- Extract connection count ----
    conn_match = re.search(r"(\d+)\+?\s*connections?", pdf_text, re.IGNORECASE)
    if conn_match:
        metadata["connection_count"] = int(conn_match.group(1))

    # ---- Heuristically calculate experience years ----
    year_ranges = re.findall(r"(\b20\d{2}\b)\s*[-\u2013\u2014]\s*(\b20\d{2}\b|Present)", pdf_text, re.IGNORECASE)
    total_years = 0.0
    current_year = datetime.date.today().year

    for start, end in year_ranges:
        start_yr = int(start)
        end_yr = current_year if end.lower() == "present" else int(end)
        diff = end_yr - start_yr
        if 0 < diff < 20:  # Sanity filter
            total_years += diff

    if total_years > 0:
        metadata["years_experience"] = round(min(total_years, 35.0), 1)

    return metadata
