"""
Grounding evaluation.

The claim this feature makes is that a supported claim has real evidence behind
it, so the tests concentrate on the part that has to be true for the number to
mean anything: a quoted span is checked against the source by string comparison,
and a model asserting support without producing a real quote is overruled.

The model calls are stubbed. This suite costs nothing to run and does not depend
on what any particular model happens to answer.
"""
from _harness import Results
import grounding as G

r = Results()


class _StubGemini:
    """Replaces _call_gemini with canned JSON, and records what it was asked."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, api_key, system_instruction, prompt, json_mode=False):
        self.calls += 1
        if not self.responses:
            raise AssertionError("stub called more times than it has responses")
        out = self.responses.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def run():
    SOURCE = (
        "Experience\nZUZU\nAI Engineer Intern\nMarch 2026 - Present (5 months)\n"
        "- Build an AI-powered student onboarding platform using Next.js, FastAPI,\n"
        "PostgreSQL/pgvector, OpenAI, and Gemini.\n"
    )
    TWIN = "Rishindra Mateti. M.S. Computer Science student at Wright State University."

    # ---- span checking: the deterministic core ----
    span_cases = [
        ("verbatim quote", "AI Engineer Intern", SOURCE, "exact"),
        ("quote across a line break", "onboarding platform using Next.js, FastAPI, PostgreSQL/pgvector", SOURCE, "exact"),
        ("case and spacing normalised", "ai engineer    intern", SOURCE, "exact"),
        ("content words present, reordered", "FastAPI PostgreSQL onboarding platform", SOURCE, "loose"),
        ("fabricated quote", "led a team of twelve engineers at Google", SOURCE, "absent"),
        ("plausible but not present", "AI Engineer Intern at Microsoft", SOURCE, "absent"),
        ("empty span", "", SOURCE, "absent"),
        ("span but empty source", "AI Engineer Intern", "", "absent"),
        ("two words is not evidence", "Gemini OpenAI", SOURCE, "absent"),
    ]
    for label, span, source, expected in span_cases:
        got = G.check_span(span, source)
        r.check(f"span check: {label}", got == expected, f"expected {expected}, got {got}")

    # ---- a model claiming support without real evidence is overruled ----
    original = G._call_gemini
    try:
        claims = [
            {"variant": "referral", "claim": "Works as an AI Engineer Intern at ZUZU", "subject": "candidate"},
            {"variant": "referral", "claim": "Led a team of twelve engineers at Google", "subject": "candidate"},
        ]
        G._call_gemini = _StubGemini(
            '{"results": ['
            '{"index": 0, "verdict": "supported", "span": "AI Engineer Intern"},'
            '{"index": 1, "verdict": "supported", "span": "led a team of twelve engineers at Google"}'
            "]}"
        )
        verified = G.verify_claims("k", claims, SOURCE, TWIN)

        r.check("real quote is accepted", verified[0]["supported"] is True, "grounded claim rejected")
        r.check(
            "invented quote is rejected despite a 'supported' verdict",
            verified[1]["supported"] is False,
            "a fabricated span was accepted",
        )
        r.check(
            "overruling the model is recorded",
            verified[1]["model_overruled"] is True and verified[0]["model_overruled"] is False,
            "overrule not flagged",
        )
        r.check(
            "no span is kept for an unsupported claim",
            verified[1]["span"] == "",
            "an unverified span was stored as evidence",
        )

        # ---- claims are graded against the right document ----
        G._call_gemini = _StubGemini(
            '{"results": [{"index": 0, "verdict": "supported", "span": "AI Engineer Intern"}]}'
        )
        wrong_doc = G.verify_claims(
            "k",
            [{"variant": "referral", "claim": "The sender is an AI Engineer Intern", "subject": "sender"}],
            SOURCE,
            TWIN,
        )
        r.check(
            "a sender claim is not grounded by the candidate's document",
            wrong_doc[0]["supported"] is False,
            "sources were crossed",
        )

        # ---- non-factual text is excluded, not counted as ungrounded ----
        G._call_gemini = _StubGemini('{"results": []}')
        pleasantries = G.verify_claims(
            "k",
            [{"variant": "coffee", "claim": "Would be grateful for a short chat", "subject": "neither"}],
            SOURCE,
            TWIN,
        )
        r.check(
            "an ask is not scored as a factual claim",
            pleasantries == [],
            "a request was scored for grounding",
        )

        # ---- scoring ----
        summary = G.score_results([
            {"subject": "candidate", "supported": True, "match": "exact", "model_overruled": False},
            {"subject": "candidate", "supported": False, "match": "absent", "model_overruled": True},
            {"subject": "sender", "supported": True, "match": "loose", "model_overruled": False},
        ])
        r.check("claims counted", summary["claims_checked"] == 3, f"got {summary['claims_checked']}")
        r.check("grounded rate", summary["grounded_rate"] == round(2 / 3, 4), f"got {summary['grounded_rate']}")
        r.check("overrules counted", summary["model_overruled"] == 1, f"got {summary['model_overruled']}")
        r.check(
            "rates split by subject",
            summary["by_subject"]["candidate"]["grounded_rate"] == 0.5
            and summary["by_subject"]["sender"]["grounded_rate"] == 1.0,
            "subject split wrong",
        )

        # ---- unreadable output refuses to answer; readable output is parsed ----
        # The split matters: output that cannot be parsed tells us nothing and
        # must not score as "this draft asserts nothing", whereas well-formed
        # output of an unexpected shape genuinely contains no usable claims.
        for label, response in [
            ("prose instead of JSON", "I could not do that."),
            ("truncated JSON", '{"claims": [{"variant": "referral", "claim"'),
        ]:
            G._call_gemini = _StubGemini(response)
            try:
                G.extract_claims("k", {"referral": "hi"}, "Someone", "Sender")
                r.check(f"unreadable output refuses to answer: {label}", False, "returned a clean sheet")
            except G.GroundingUnavailable:
                r.check(f"unreadable output refuses to answer: {label}", True, "")
            except Exception as exc:
                r.check(f"unreadable output refuses to answer: {label}", False, f"{type(exc).__name__}: {exc}")

        for label, response in [
            ("wrong shape", '{"claims": "not a list"}'),
            ("fenced output", '```json\n{"claims": []}\n```'),
            ("claims missing entirely", '{"something_else": 1}'),
        ]:
            G._call_gemini = _StubGemini(response)
            try:
                out = G.extract_claims("k", {"referral": "hi"}, "Someone", "Sender")
                r.check(f"parseable output yields a list: {label}", isinstance(out, list), "did not return a list")
            except Exception as exc:
                r.check(f"parseable output yields a list: {label}", False, f"{type(exc).__name__}: {exc}")

        G._call_gemini = _StubGemini(RuntimeError("network down"), RuntimeError("network down"))
        report = G.evaluate_drafts("k", {"referral": "hi"}, SOURCE, TWIN, "Someone", "Sender")
        r.check(
            "a failed evaluation never raises",
            isinstance(report, dict) and report["claims"] == [],
            "evaluation raised or returned junk",
        )

        # ---- an outage must not be reported as fabrication ----
        # A real 503 run scored six profiles at "0% grounded" before this: the
        # verification call failed, every claim defaulted to unsupported, and
        # the result was indistinguishable from drafts full of invention.
        G._call_gemini = _StubGemini(RuntimeError("503 UNAVAILABLE"))
        try:
            G.extract_claims("k", {"referral": "hi"}, "Someone", "Sender")
            r.check("a failed extraction refuses to answer", False, "returned a clean sheet instead of raising")
        except G.GroundingUnavailable:
            r.check("a failed extraction refuses to answer", True, "")

        G._call_gemini = _StubGemini(RuntimeError("503 UNAVAILABLE"))
        try:
            G.verify_claims(
                "k",
                [{"variant": "referral", "claim": "Works at ZUZU", "subject": "candidate"}],
                SOURCE, TWIN,
            )
            r.check("a failed verification refuses to answer", False, "marked claims unsupported on an outage")
        except G.GroundingUnavailable:
            r.check("a failed verification refuses to answer", True, "")

        G._call_gemini = _StubGemini(
            '{"claims": [{"variant": "referral", "claim": "Works at ZUZU", "subject": "candidate"}]}',
            RuntimeError("503 UNAVAILABLE"),
        )
        outage = G.evaluate_drafts("k", {"referral": "hi"}, SOURCE, TWIN, "Someone", "Sender")
        r.check("an outage reports unavailable", outage.get("unavailable") is True, "not flagged unavailable")
        r.check("an outage carries no summary", outage["summary"] is None, "an outage produced a score")
        r.check(
            "an outage is not a 0% grounded rate",
            not outage.get("ok"),
            "an unavailable check was presented as a result",
        )
        r.check(
            "an outage never triggers a rewrite",
            G.regeneration_feedback(outage) is None,
            "would have regenerated on an outage",
        )

        # ---- the whole path, end to end ----
        G._call_gemini = _StubGemini(
            '{"claims": ['
            '{"variant": "referral", "claim": "Works as an AI Engineer Intern", "subject": "candidate"},'
            '{"variant": "referral", "claim": "Runs a hedge fund", "subject": "candidate"},'
            '{"variant": "coffee", "claim": "Would love a quick chat", "subject": "neither"}'
            "]}",
            '{"results": ['
            '{"index": 0, "verdict": "supported", "span": "AI Engineer Intern"},'
            '{"index": 1, "verdict": "supported", "span": "runs a hedge fund in Connecticut"}'
            "]}",
        )
        full = G.evaluate_drafts("k", {"referral": "x", "coffee": "y"}, SOURCE, TWIN, "Someone", "Sender")
        r.check("end to end reports ok", full["ok"] is True, "report not ok")
        r.check("end to end counts one grounded", full["summary"]["supported"] == 1, f"got {full['summary']['supported']}")
        r.check("end to end counts one ungrounded", full["summary"]["unsupported"] == 1, f"got {full['summary']['unsupported']}")
        r.check("non-factual claims counted separately", full["non_factual_claims"] == 1, "ask miscounted")
        r.check(
            "two model calls for a whole set of drafts",
            G._call_gemini.calls == 2,
            f"made {G._call_gemini.calls} calls",
        )

        # ---- the correction instruction names the offending claim ----
        feedback = G.regeneration_feedback(full)
        r.check("feedback produced when a claim is unsupported", bool(feedback), "no feedback")
        r.check("feedback names the specific claim", "hedge fund" in feedback, "claim not named")
        r.check("feedback does not name grounded claims", "AI Engineer Intern" not in feedback, "grounded claim named")

        clean = {"ok": True, "summary": {"unsupported": 0}, "unsupported_by_variant": {}}
        r.check(
            "no feedback when everything is grounded",
            G.regeneration_feedback(clean) is None,
            "asked for a rewrite with nothing to fix",
        )
        r.check(
            "no feedback from a failed report",
            G.regeneration_feedback({"ok": False}) is None,
            "acted on a failed evaluation",
        )
    finally:
        G._call_gemini = original

    # ---- the retry is bounded and only kept when it helps ----
    from orchestrator import QueueOrchestrator as Q

    worse = {"ok": True, "summary": {"unsupported": 5, "grounded_rate": 0.2}}
    better = {"ok": True, "summary": {"unsupported": 1, "grounded_rate": 0.9}}
    same = {"ok": True, "summary": {"unsupported": 5, "grounded_rate": 0.5}}
    r.check("a better rewrite is kept", Q._is_better(better, worse) is True, "improvement rejected")
    r.check("a worse rewrite is discarded", Q._is_better(worse, better) is False, "regression accepted")
    r.check("an equal rewrite is discarded", Q._is_better(same, worse) is False, "no-op accepted")
    r.check("a failed recheck is discarded", Q._is_better({"ok": False}, worse) is False, "failed recheck accepted")

    # ---- the grounding step can never cost the user their drafts ----
    # Left inline in the worker, a quota error during the correction pass would
    # reach the failure handler, cooldown the key for three minutes and re-run
    # the whole six-call pipeline, discarding drafts that had already succeeded.
    import asyncio
    import os
    import orchestrator as O

    DRAFTS = {k: f"draft {k}" for k in G.VARIANT_KEYS}

    class _Conn2:
        name = "Someone"
        profile_text = "source text"
        posts_text = ""

    def _run(coro):
        return asyncio.new_event_loop().run_until_complete(coro)

    def _ground(**over):
        args = dict(
            worker_name="W", api_key="k", connection=_Conn2(), variants=dict(DRAFTS),
            bridge_data={}, twin_profile="twin", tone_examples="", sender_name="S",
        )
        args.update(over)
        return _run(O.QueueOrchestrator()._ground_and_correct(**args))

    real_eval, real_gen = O.evaluate_drafts, O.generate_outreach_variants
    try:
        # An exception anywhere in the step is swallowed and the drafts survive.
        def _boom(**kw):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        O.evaluate_drafts = _boom
        kept, rep = _ground()
        r.check("a failed check keeps the drafts", kept == DRAFTS, "drafts were lost")
        r.check("a failed check reports nothing", rep is None, "invented a report")

        # A quota error in the *correction* pass is the dangerous one: the
        # check already succeeded, so the drafts must still survive.
        O.evaluate_drafts = lambda **kw: {
            "ok": True,
            "summary": {"unsupported": 2, "grounded_rate": 0.5},
            "unsupported_by_variant": {"referral": ["made up thing"]},
            "claims": [],
        }
        O.generate_outreach_variants = _boom
        kept, rep = _ground()
        r.check("a failed rewrite keeps the original drafts", kept == DRAFTS, "drafts were lost")
        r.check("a failed rewrite keeps the check result", rep is not None and rep["ok"], "report discarded")

        # A rewrite that grounds worse is rejected, and the originals stand.
        O.generate_outreach_variants = lambda **kw: {k: "worse " + k for k in G.VARIANT_KEYS}
        calls = {"n": 0}

        def _eval_pair(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"ok": True, "summary": {"unsupported": 2, "grounded_rate": 0.5},
                        "unsupported_by_variant": {"referral": ["made up"]}, "claims": []}
            return {"ok": True, "summary": {"unsupported": 4, "grounded_rate": 0.2},
                    "unsupported_by_variant": {"referral": ["worse"]}, "claims": []}
        O.evaluate_drafts = _eval_pair
        kept, rep = _ground()
        r.check("a worse rewrite is discarded", kept == DRAFTS, "kept a regression")
        r.check("the rejection is recorded", rep.get("regeneration_rejected") is True, "not recorded")

        # A rewrite that grounds better replaces them.
        calls["n"] = 0

        def _eval_pair_better(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"ok": True, "summary": {"unsupported": 4, "grounded_rate": 0.2},
                        "unsupported_by_variant": {"referral": ["made up"]}, "claims": []}
            return {"ok": True, "summary": {"unsupported": 0, "grounded_rate": 1.0},
                    "unsupported_by_variant": {}, "claims": []}
        O.evaluate_drafts = _eval_pair_better
        kept, rep = _ground()
        r.check("a better rewrite is adopted", kept != DRAFTS, "improvement discarded")
        r.check("the rewrite is recorded", rep.get("regenerated") is True, "not recorded")

        # ---- the environment switches actually stop the spend ----
        spend = {"n": 0}

        def _counting_eval(**kw):
            spend["n"] += 1
            return {"ok": True, "summary": {"unsupported": 1, "grounded_rate": 0.5},
                    "unsupported_by_variant": {"referral": ["x"]}, "claims": []}
        O.evaluate_drafts = _counting_eval
        O.generate_outreach_variants = lambda **kw: dict(DRAFTS)

        os.environ["GROUNDING_ENABLED"] = "false"
        kept, rep = _ground()
        r.check("GROUNDING_ENABLED=false spends nothing", spend["n"] == 0, f"made {spend['n']} calls")
        r.check("GROUNDING_ENABLED=false keeps the drafts", kept == DRAFTS, "drafts changed")
        del os.environ["GROUNDING_ENABLED"]

        spend["n"] = 0
        os.environ["GROUNDING_AUTOCORRECT"] = "off"
        kept, rep = _ground()
        r.check("GROUNDING_AUTOCORRECT=off still measures", spend["n"] == 1, f"made {spend['n']} calls")
        r.check("GROUNDING_AUTOCORRECT=off skips the rewrite", kept == DRAFTS, "rewrote anyway")
        del os.environ["GROUNDING_AUTOCORRECT"]

        spend["n"] = 0
        kept, rep = _ground()
        r.check("both on: check plus recheck", spend["n"] == 2, f"made {spend['n']} calls")
    finally:
        O.evaluate_drafts, O.generate_outreach_variants = real_eval, real_gen
        os.environ.pop("GROUNDING_ENABLED", None)
        os.environ.pop("GROUNDING_AUTOCORRECT", None)

    # ---- the source the drafts are checked against excludes the agents' own output ----
    class _Conn:
        profile_text = "the real profile"
        posts_text = "the real posts"
        profile_intelligence = '{"company": "an invented company"}'
        company_intelligence = '{"summary": "invented company background"}'

    source = Q._candidate_source(_Conn())
    r.check(
        "source is the raw profile and posts",
        "the real profile" in source and "the real posts" in source,
        "source missing raw material",
    )
    r.check(
        "agent output is not its own evidence",
        "invented" not in source,
        "an agent's own JSON was included as source material",
    )

    return r.report("grounding evaluation")


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
