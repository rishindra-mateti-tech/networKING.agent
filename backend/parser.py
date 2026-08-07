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
        "profile_url": None
    }

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
    for line in lines[name_line_idx + 1: name_line_idx + 6]:
        if is_section_header(line):
            break
        # Skip lines that look like URLs or email addresses
        if "@" in line or "linkedin.com" in line.lower():
            continue
        # Skip lines that are just numbers (connection counts, etc.)
        if re.match(r"^\d+\s*(connections?|followers?)?$", line, re.IGNORECASE):
            continue
        headline_lines.append(line)

    if headline_lines:
        metadata["current_title"] = headline_lines[0]
        # Look for "at [Company]" pattern in headline
        company_match = re.search(r"\bat\s+(.+)$", headline_lines[0], re.IGNORECASE)
        if company_match:
            metadata["company"] = company_match.group(1).strip()
        elif len(headline_lines) > 1:
            # Second headline line is often the company name
            potential_company = headline_lines[1]
            # Only assign if it's short enough to be a company name
            if len(potential_company) < 80:
                metadata["company"] = potential_company

    # ---- Extract location ----
    # LinkedIn PDFs often place location near the top, identified by patterns like:
    # "City, State", "City, Country", "Greater X Area", or common location suffixes
    location_patterns = [
        r"(?:greater\s+)?[\w\s]+,\s*[\w\s]+(?:\s+area)?",  # City, State/Country
        r"[\w\s]+\s+(?:area|metro|region)",                  # X Area/Metro
    ]
    us_states = [
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
        # Abbreviations
        "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
        "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
        "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
        "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
        "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy"
    ]
    countries = [
        "united states", "usa", "india", "canada", "united kingdom", "uk",
        "australia", "germany", "france", "singapore", "japan", "china",
        "brazil", "netherlands", "ireland", "israel", "south korea", "sweden"
    ]

    for line in lines[name_line_idx + 1: name_line_idx + 10]:
        lowered = line.lower()
        if is_section_header(line):
            continue
        if "@" in line or "linkedin.com" in lowered:
            continue

        # Check for "area" or "greater" patterns
        if "area" in lowered or "greater" in lowered:
            metadata["location"] = line
            break

        # Check for "City, State" or "City, Country" patterns
        if "," in line:
            parts = [p.strip().lower() for p in line.split(",")]
            for part in parts:
                if part in us_states or part in countries:
                    metadata["location"] = line
                    break
            if metadata["location"]:
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
