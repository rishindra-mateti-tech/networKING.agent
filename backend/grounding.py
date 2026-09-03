"""
Grounding evaluation for generated outreach drafts.

The pipeline asserts that it researches a person. Nothing until now checked
whether what it then wrote about them was actually in the source material, and
the failure this catches is not hypothetical: a draft opened by calling its
sender "a software engineer with a Master's in Computer Science" when the
profile says he is a current M.S. student who has not graduated. Sending an
invented fact to a real stranger is the worst thing this product can do, and it
was completely unmeasured.

The design point that makes the number defensible: the model is never asked
"is this claim true?" and believed. It is asked to quote the span of source
text that supports the claim, and that quote is then checked against the source
by string comparison. A model that invents its own evidence fails the check, so
the final adjudication is deterministic rather than an LLM's opinion of its own
work. Claims are extracted and verified in two batched calls for a whole set of
drafts, not one call per claim, because this runs on a free-tier key.
"""

import json
import re
from typing import Optional

from generator import _call_gemini, _strip_json_codeblock

# The five drafts the message writing agent produces.
VARIANT_KEYS = ["referral", "coffee", "technical", "relationship", "featured"]


class GroundingUnavailable(Exception):
    """
    The check could not be carried out.

    Distinct from "the claims were checked and found unsupported", and the
    distinction is the whole point: when the verification call failed, every
    claim came back marked unsupported, which reads identically to a draft full
    of fabrications. A transient API outage was reported as 0% grounded. A
    measurement that cannot tell "no evidence" from "no answer" is exactly the
    thing this module exists to stop, so the two are now separate outcomes and
    an unavailable check reports nothing rather than zero.
    """

# Words too common to count as evidence when falling back to token overlap.
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "has", "had",
    "was", "were", "are", "been", "being", "their", "there", "they", "them",
    "you", "your", "his", "her", "its", "our", "who", "which", "what", "when",
    "where", "how", "why", "into", "onto", "over", "under", "about", "after",
    "before", "than", "then", "also", "some", "more", "most", "such", "very",
    "just", "only", "both", "each", "other", "will", "would", "could", "should",
}


def _normalize(text: str) -> str:
    """
    Collapses a string to a form that survives PDF extraction.

    A LinkedIn export breaks sentences across hard line breaks at arbitrary
    points, so a span quoted as one phrase will not match the source character
    for character even when it is genuinely there. Whitespace and case are
    flattened; nothing else is.
    """
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip().lower()


def _content_tokens(text: str) -> list:
    """The words in a string that carry enough meaning to serve as evidence."""
    words = re.findall(r"[a-z0-9]+", _normalize(text))
    return [w for w in words if len(w) > 3 and w not in _STOPWORDS]


def check_span(span: str, source: str) -> str:
    """
    Decides whether a quoted span really occurs in the source.

    Returns "exact" when the normalized span appears verbatim, "loose" when
    every content word of a substantial span appears somewhere in the source
    (which covers a quote reassembled across a line break or with typography
    normalized), and "absent" otherwise. "absent" is what a fabricated quote
    gets, and it is the whole reason this function exists rather than trusting
    the model's verdict directly.
    """
    if not span or not source:
        return "absent"

    span_norm = _normalize(span)
    source_norm = _normalize(source)
    if span_norm and span_norm in source_norm:
        return "exact"

    tokens = _content_tokens(span)
    # A one or two word "quote" is not evidence of anything; require a real
    # phrase before accepting an out-of-order match.
    if len(tokens) >= 3:
        source_tokens = set(_content_tokens(source))
        if all(t in source_tokens for t in tokens):
            return "loose"
    return "absent"


def extract_claims(
    api_key: str,
    drafts: dict,
    candidate_name: str,
    sender_name: str,
) -> list:
    """
    Pulls the checkable factual assertions out of a whole set of drafts at once.

    Each claim is tagged with who it is about, because they are grounded against
    different sources: what the draft says about the candidate must come from
    their profile, and what it says about the sender must come from the sender's
    own TwinAgent profile. Asks, pleasantries and opinions are tagged "neither"
    and excluded from scoring rather than counted as ungrounded.
    """
    present = {k: v for k, v in drafts.items() if v and str(v).strip()}
    if not present:
        return []

    numbered = "\n\n".join(f"[{k}]\n{v}" for k, v in present.items())

    system_instruction = (
        "You extract factual claims from text. You do not judge whether they are true. "
        "You return only raw JSON."
    )
    prompt = f"""
Below are outreach message drafts. The sender is {sender_name}. The recipient is {candidate_name}.

For every draft, list each CHECKABLE FACTUAL CLAIM it makes. A checkable factual claim
asserts something specific that could be confirmed or contradicted by a document: a job
title, an employer, a school, a degree, a technology someone works with, a project, a
publication, a length of time, an achievement.

These are NOT claims, and must be excluded:
- requests, questions and offers ("would you be open to a short chat")
- opinions, compliments and hedges ("your work looks interesting", "no pressure")
- statements about the sender's intentions or feelings ("I would be grateful to learn")
- generic pleasantries

Tag each claim with its subject:
- "candidate" if it asserts something about {candidate_name}
- "sender" if it asserts something about {sender_name}
- "neither" if it is about anything else

DRAFTS:
{numbered}

Return ONLY raw JSON in this exact shape, with no markdown fence:
{{"claims": [{{"variant": "<the bracketed label the claim came from>", "claim": "<the assertion, in one short sentence>", "subject": "candidate|sender|neither"}}]}}
"""

    try:
        raw = _call_gemini(api_key, system_instruction, prompt, json_mode=True)
        data = json.loads(_strip_json_codeblock(raw))
    except Exception as e:
        # Returning [] here would read as "the drafts make no claims", which
        # scores as a clean sheet. Refuse to answer instead.
        raise GroundingUnavailable(f"claim extraction failed: {e}") from e

    claims = []
    for item in (data.get("claims") or []):
        if not isinstance(item, dict):
            continue
        text = (item.get("claim") or "").strip()
        if not text:
            continue
        variant = (item.get("variant") or "").strip().strip("[]")
        subject = (item.get("subject") or "neither").strip().lower()
        if subject not in ("candidate", "sender", "neither"):
            subject = "neither"
        claims.append({
            "variant": variant if variant in present else "unknown",
            "claim": text,
            "subject": subject,
        })
    return claims


def verify_claims(
    api_key: str,
    claims: list,
    candidate_source: str,
    sender_source: str,
) -> list:
    """
    Asks for the supporting quote behind each claim, then checks the quote itself.

    The model's own verdict is recorded but never trusted on its own: a claim is
    only counted as supported when the span it cited is actually found in the
    source by check_span. This is what stops the evaluation from degenerating
    into one model grading another model's homework.
    """
    checkable = [c for c in claims if c["subject"] in ("candidate", "sender")]
    if not checkable:
        return []

    listed = "\n".join(
        f"{i}. [{c['subject']}] {c['claim']}" for i, c in enumerate(checkable)
    )

    system_instruction = (
        "You verify claims against source documents by quoting evidence. "
        "You never paraphrase a quote. You return only raw JSON."
    )
    prompt = f"""
CANDIDATE SOURCE DOCUMENT:
{candidate_source or "(no candidate source available)"}

SENDER SOURCE DOCUMENT:
{sender_source or "(no sender source available)"}

For each claim below, find the passage in the matching source document that supports it.
A claim tagged [candidate] must be supported by the CANDIDATE source document.
A claim tagged [sender] must be supported by the SENDER source document.

Copy the supporting passage EXACTLY as it appears in the document, character for character.
Do not paraphrase it, do not clean it up, do not summarise it, do not join separate
passages together. If no single passage in the correct document supports the claim,
return an empty string for the span and "unsupported" as the verdict. Guessing a
plausible-sounding quote is worse than returning nothing.

CLAIMS:
{listed}

Return ONLY raw JSON in this exact shape, with no markdown fence:
{{"results": [{{"index": <the claim's number>, "verdict": "supported|unsupported", "span": "<exact quote, or empty string>"}}]}}
"""

    try:
        raw = _call_gemini(api_key, system_instruction, prompt, json_mode=True)
        data = json.loads(_strip_json_codeblock(raw))
        by_index = {}
        for item in (data.get("results") or []):
            if isinstance(item, dict) and item.get("index") is not None:
                try:
                    by_index[int(item["index"])] = item
                except (TypeError, ValueError):
                    continue
    except Exception as e:
        raise GroundingUnavailable(f"claim verification failed: {e}") from e

    out = []
    for i, claim in enumerate(checkable):
        item = by_index.get(i, {})
        span = (item.get("span") or "").strip()
        model_verdict = (item.get("verdict") or "unsupported").strip().lower()
        source = candidate_source if claim["subject"] == "candidate" else sender_source
        match = check_span(span, source)

        # The span decides, not the model. A "supported" verdict whose quote is
        # nowhere in the document is exactly the failure being measured.
        supported = match in ("exact", "loose")
        out.append({
            **claim,
            "supported": supported,
            "match": match,
            "span": span if supported else "",
            "model_said": model_verdict,
            # Recorded so the gap between what the model claimed and what the
            # text actually shows is visible rather than silently resolved.
            "model_overruled": (model_verdict == "supported") and not supported,
        })
    return out


def score_results(results: list) -> dict:
    """Aggregates verified claims into the rates the report is built from."""
    total = len(results)
    supported = sum(1 for r in results if r["supported"])
    by_subject = {}
    for subject in ("candidate", "sender"):
        subset = [r for r in results if r["subject"] == subject]
        by_subject[subject] = {
            "total": len(subset),
            "supported": sum(1 for r in subset if r["supported"]),
            "grounded_rate": round(
                sum(1 for r in subset if r["supported"]) / len(subset), 4
            ) if subset else None,
        }
    return {
        "claims_checked": total,
        "supported": supported,
        "unsupported": total - supported,
        "grounded_rate": round(supported / total, 4) if total else None,
        "exact_matches": sum(1 for r in results if r["match"] == "exact"),
        "loose_matches": sum(1 for r in results if r["match"] == "loose"),
        "model_overruled": sum(1 for r in results if r["model_overruled"]),
        "by_subject": by_subject,
    }


def evaluate_drafts(
    api_key: str,
    drafts: dict,
    candidate_source: str,
    sender_source: str,
    candidate_name: str,
    sender_name: str = "the sender",
) -> dict:
    """
    Runs the whole check over one set of drafts. Two model calls, whatever the
    number of drafts or claims.

    Never raises: a failure here must not cost the user their drafts, so an
    error returns an empty report and the caller carries on with what it has.
    """
    try:
        claims = extract_claims(api_key, drafts, candidate_name, sender_name)
        results = verify_claims(api_key, claims, candidate_source, sender_source)
    except GroundingUnavailable as e:
        print(f"[GROUNDING] Check unavailable, reporting nothing rather than zero: {e}")
        return {"ok": False, "unavailable": True, "error": str(e), "claims": [], "summary": None}
    except Exception as e:
        print(f"[GROUNDING] Evaluation failed: {e}")
        return {"ok": False, "unavailable": True, "error": str(e), "claims": [], "summary": None}

    summary = score_results(results)
    by_variant = {}
    for r in results:
        by_variant.setdefault(r["variant"], []).append(r)

    return {
        "ok": True,
        "claims": results,
        "summary": summary,
        "unsupported_by_variant": {
            variant: [r["claim"] for r in rows if not r["supported"]]
            for variant, rows in by_variant.items()
            if any(not r["supported"] for r in rows)
        },
        "non_factual_claims": sum(1 for c in claims if c["subject"] == "neither"),
    }


def regeneration_feedback(report: dict) -> Optional[str]:
    """
    Turns unsupported claims into an instruction for a second writing pass.

    Names the specific assertions rather than saying "be more accurate", because
    a general instruction to be careful reliably produces a differently-worded
    version of the same invention.
    """
    if not report or not report.get("ok"):
        return None
    offenders = report.get("unsupported_by_variant") or {}
    if not offenders:
        return None

    lines = []
    for variant, claims in offenders.items():
        for claim in claims:
            lines.append(f'- In the "{variant}" draft: {claim}')

    return (
        "A previous version of these drafts asserted the following things, none of which "
        "appear anywhere in the source material provided above:\n"
        + "\n".join(lines)
        + "\n\nRewrite so that every factual statement about the recipient or about the sender "
        "is traceable to the source material. Do not restate any of the above, and do not "
        "substitute a differently-worded version of the same unsupported idea. Where you have "
        "no grounded specific to point at, write something more general that is true rather "
        "than inventing a specific that is not."
    )
