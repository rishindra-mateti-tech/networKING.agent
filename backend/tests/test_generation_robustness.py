"""
Generation robustness.

The model is the least predictable dependency in the system: it can return
prose instead of JSON, truncate mid-object, or wrap output in fences. When it
does, a worker must still produce a usable record rather than raise and strand
the connection mid-pipeline. Every agent is therefore fed deliberately broken
output with the network call stubbed out, so none of this costs a real call.

Also covers Telegram packing, where a draft is wrapped in a tag that spans
newlines and a naive split would emit an unclosed tag and be rejected outright.
"""
import html

from _harness import Results
import generator as G
from orchestrator import QueueOrchestrator

r = Results()

BROKEN_MODEL_OUTPUT = {
    "empty": "",
    "whitespace": "   \n  ",
    "prose instead of json": "Sure! Here is your email.",
    "truncated json": '{"subject": "hi", "bod',
    "null fields": '{"subject": null, "body": null}',
    "wrong field types": '{"subject": 123, "body": ["a","b"]}',
    "missing fields": '{"foo": "bar"}',
    "fenced json": '```json\n{"subject":"s","body":"b"}\n```',
    "double fenced": '```\n```json\n{"subject":"s","body":"b"}\n```\n```',
    "json array": '[{"subject":"s","body":"b"}]',
    "unicode escapes": '{"subject":"\\u0041","body":"\\ud83d\\ude00"}',
    "enormous": '{"subject":"' + "x" * 50000 + '","body":"y"}',
    "markup inside json": '{"subject":"<script>x</script>","body":"<b>hi</b>"}',
}


def run():
    for label, output in BROKEN_MODEL_OUTPUT.items():
        G._call_gemini = lambda *a, **k: output

        try:
            email = G.generate_outreach_email(
                api_key="stub", twin_profile="t", candidate_name="C",
                candidate_email="c@example.com", candidate_profile="p",
                bridge_data={}, tone_examples="", sender_name="S",
            )
            r.check(
                f"email generation survives: {label}",
                isinstance(email, dict) and isinstance(email.get("subject"), str)
                and isinstance(email.get("body"), str),
                f"got {email!r}"[:160],
            )
        except Exception as exc:
            r.check(f"email generation survives: {label}", False, f"{type(exc).__name__}: {exc}")

        try:
            variants = G.run_message_writing_agent(
                api_key="stub", profile_json={"name": "C", "company": "Co"},
                company_json={}, strategy_json={}, personalization_json={},
                context_summary="", twin_profile="t", tone_examples="", sender_name="S",
            )
            r.check(
                f"message drafts survive: {label}",
                isinstance(variants, dict) and all(isinstance(v, str) for v in variants.values()),
                "non-string draft returned",
            )
        except Exception as exc:
            r.check(f"message drafts survive: {label}", False, f"{type(exc).__name__}: {exc}")

        try:
            profile = G.run_profile_intelligence_agent("stub", "Name", "text", "posts")
            r.check(
                f"profile analysis survives: {label}",
                isinstance(profile, dict) and isinstance(profile.get("years_experience"), float),
                "bad shape or non-float experience",
            )
        except Exception as exc:
            r.check(f"profile analysis survives: {label}", False, f"{type(exc).__name__}: {exc}")

    # ---- bracketed placeholders must never reach a draft the user sends ----
    G._call_gemini = lambda *a, **k: (
        "[REFERRAL_DRAFT]\nHi [Name], I'm [Your Name] at [Your Company] working as [Role].\n"
        "[COFFEE_CHAT_DRAFT]\nHey [Name] at [Company].\n"
        "[TECHNICAL_DRAFT]\nt\n[RELATIONSHIP_BUILDING_DRAFT]\nr\n[FEATURED_DRAFT]\nf\n"
    )
    drafts = G.run_message_writing_agent(
        api_key="stub", profile_json={"name": "Dana Reed", "company": "Acme"},
        company_json={}, strategy_json={}, personalization_json={},
        context_summary="", twin_profile="t", tone_examples="", sender_name="Sam Patel",
    )
    combined = " ".join(drafts.values())
    for placeholder in ("[Name]", "[Company]", "[Your Name]", "[Your Company]", "[Role]"):
        r.check(f"placeholder {placeholder} replaced", placeholder not in combined, combined[:200])
    r.check("candidate name substituted", "Dana Reed" in drafts["referral"], drafts["referral"][:160])
    r.check("sender name substituted", "Sam Patel" in drafts["referral"], drafts["referral"][:160])

    # ---- telegram packing ----
    limit = QueueOrchestrator.TELEGRAM_LIMIT
    cases = {
        "unclosed tag": ["<b>unclosed", "normal"],
        "oversized code block": ["<code>" + "x" * 9000 + "</code>"],
        "all empty": ["", "", ""],
        "just under limit": ["a" * (limit - 1)],
        "exactly at limit": ["a" * limit],
        "just over limit": ["a" * (limit + 1)],
        "only newlines": ["\n" * 5000],
        "wide characters": ["😀" * 3000],
    }
    for label, blocks in cases.items():
        try:
            parts = QueueOrchestrator._pack_blocks(blocks, limit)
            oversized = [len(p) for p in parts if len(p) > limit]
            r.check(f"telegram packing respects the limit: {label}", not oversized, f"oversized parts {oversized}")
        except Exception as exc:
            r.check(f"telegram packing respects the limit: {label}", False, f"{type(exc).__name__}: {exc}")

    short = QueueOrchestrator._pack_blocks(["header", "a short featured draft"], limit)
    r.check("a short briefing stays in one message", len(short) == 1, f"split into {len(short)}")

    escaped = html.escape('<b>x</b><script>alert(1)</script>')
    r.check("markup in a candidate name is escaped", "<script>" not in escaped, escaped)

    return r.report("generation robustness and notification packing")


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
