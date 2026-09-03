"""
Measures how much of what the drafts assert is actually in the source material.

Run it:

    python evaluate_grounding.py                  # score the stored drafts
    python evaluate_grounding.py --baseline       # also score a single-prompt control
    python evaluate_grounding.py --limit 5        # stop after 5 profiles
    python evaluate_grounding.py --json out.json  # write the full per-claim record

The number this prints is the one worth quoting, because the adjudication is not
a model's opinion: every claim counted as supported has a quoted span that was
found in the source document by string comparison (see grounding.check_span).

--baseline is the honest comparison. It generates messages from a single prompt
over the same profile, scores them with the same checker, and prints both. The
five-stage pipeline costs six model calls against the baseline's one; if it does
not ground better, that is worth knowing rather than assuming. Sample sizes here
are small -- report the n, not just the percentage.
"""

import argparse
import datetime
import json
import sys

from database import SessionLocal
import models
from grounding import VARIANT_KEYS, evaluate_drafts
from generator import generate_single_prompt_baseline
from twin_agent import compile_twin_agent_profile, get_sender_name


def _first_active_key(db, user_id):
    key = db.query(models.ApiKey).filter(
        models.ApiKey.user_id == user_id,
        models.ApiKey.is_active == True,
    ).first()
    return key.key_value if key else None


def _candidate_source(conn) -> str:
    parts = [conn.profile_text or "", conn.posts_text or ""]
    return "\n\n".join(p for p in parts if p.strip())


def _drafts_of(conn) -> dict:
    return {
        "referral": conn.generated_outreach_referral,
        "coffee": conn.generated_outreach_coffee,
        "technical": conn.generated_outreach_technical,
        "relationship": conn.generated_outreach_relationship,
        "featured": conn.generated_outreach_featured,
    }


def _accumulate(totals: dict, summary: dict, drafts: dict = None):
    if not summary:
        return
    if drafts:
        totals["drafts"] += sum(1 for v in drafts.values() if v and str(v).strip())
    totals["claims"] += summary["claims_checked"]
    totals["supported"] += summary["supported"]
    totals["exact"] += summary["exact_matches"]
    totals["loose"] += summary["loose_matches"]
    totals["overruled"] += summary["model_overruled"]
    for subject in ("candidate", "sender"):
        totals[subject]["total"] += summary["by_subject"][subject]["total"]
        totals[subject]["supported"] += summary["by_subject"][subject]["supported"]


def _blank_totals() -> dict:
    return {
        "claims": 0, "supported": 0, "exact": 0, "loose": 0, "overruled": 0, "drafts": 0,
        "candidate": {"total": 0, "supported": 0},
        "sender": {"total": 0, "supported": 0},
    }


def _rate(part: int, whole: int):
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def _print_totals(label: str, totals: dict, profiles: int):
    print(f"\n  {label}")
    print(f"    profiles scored          {profiles}")
    print(f"    claims checked           {totals['claims']}")
    print(f"    grounded                 {totals['supported']}  ({_rate(totals['supported'], totals['claims'])})")
    print(f"    ungrounded               {totals['claims'] - totals['supported']}")
    print(f"      about the recipient    {_rate(totals['candidate']['supported'], totals['candidate']['total'])}"
          f"  (n={totals['candidate']['total']})")
    print(f"      about the sender       {_rate(totals['sender']['supported'], totals['sender']['total'])}"
          f"  (n={totals['sender']['total']})")
    density = totals["claims"] / totals["drafts"] if totals["drafts"] else 0
    grounded_per_draft = totals["supported"] / totals["drafts"] if totals["drafts"] else 0
    print(f"    drafts                   {totals['drafts']}")
    print(f"    claims per draft         {density:.1f}   ({grounded_per_draft:.1f} of them grounded)")
    print(f"    evidence quality         {totals['exact']} verbatim, {totals['loose']} reassembled")
    print(f"    model claimed support")
    print(f"    but cited no real span   {totals['overruled']}")


def main():
    ap = argparse.ArgumentParser(description="Score generated drafts against their source material.")
    ap.add_argument("--user-id", type=int, default=None, help="Only this account (default: all)")
    ap.add_argument("--limit", type=int, default=None, help="Stop after N profiles")
    ap.add_argument("--baseline", action="store_true", help="Also generate and score a single-prompt control")
    ap.add_argument("--json", dest="json_out", default=None, help="Write the full per-claim record here")
    ap.add_argument("--save", action="store_true",
                    help="Persist each report onto its connection, so the app annotates the drafts")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        q = db.query(models.Connection).filter(
            models.Connection.generated_outreach_referral != None,
            models.Connection.profile_text != None,
        )
        if args.user_id:
            q = q.filter(models.Connection.user_id == args.user_id)
        rows = q.order_by(models.Connection.id.asc()).all()
        if args.limit:
            rows = rows[: args.limit]

        if not rows:
            print("No connections with both generated drafts and stored profile text.")
            print("Generate drafts for at least one profile first.")
            return 1

        pipeline_totals = _blank_totals()
        baseline_totals = _blank_totals()
        scored = 0
        baseline_scored = 0
        skipped = []
        record = []

        print(f"Scoring {len(rows)} profile(s).")
        if args.baseline:
            print("Baseline enabled: generating single-prompt control messages for each.\n")

        for conn in rows:
            api_key = _first_active_key(db, conn.user_id)
            if not api_key:
                skipped.append((conn.name, "account has no active API key"))
                print(f"  - {conn.name}: SKIPPED, account has no active API key")
                continue

            source = _candidate_source(conn)
            twin = compile_twin_agent_profile(db, conn.user_id)
            sender = get_sender_name(db, conn.user_id)

            report = evaluate_drafts(
                api_key=api_key,
                drafts=_drafts_of(conn),
                candidate_source=source,
                sender_source=twin,
                candidate_name=conn.name,
                sender_name=sender,
            )
            if not report.get("ok") or not report.get("summary"):
                # Not scored as zero. A check that could not run tells us
                # nothing about the drafts, and averaging it in as 0% would
                # manufacture exactly the kind of unbacked number this tool
                # exists to catch.
                skipped.append((conn.name, report.get("error", "unknown")))
                print(f"  - {conn.name}: SKIPPED, check unavailable")
                continue

            s = report["summary"]
            if args.save:
                # Lets a re-scored profile update its annotations without
                # regenerating the drafts themselves.
                conn.grounding_report = json.dumps(report)
                db.commit()
            _accumulate(pipeline_totals, s, _drafts_of(conn))
            scored += 1
            line = f"  - {conn.name}: {s['supported']}/{s['claims_checked']} grounded"

            entry = {"connection_id": conn.id, "name": conn.name, "pipeline": report}

            if args.baseline:
                control = generate_single_prompt_baseline(
                    api_key=api_key,
                    twin_profile=twin,
                    candidate_name=conn.name,
                    candidate_profile=conn.profile_text or "",
                    candidate_posts=conn.posts_text or "",
                    sender_name=sender,
                )
                b_report = evaluate_drafts(
                    api_key=api_key,
                    drafts=control,
                    candidate_source=source,
                    sender_source=twin,
                    candidate_name=conn.name,
                    sender_name=sender,
                )
                if b_report.get("ok") and b_report.get("summary"):
                    bs = b_report["summary"]
                    _accumulate(baseline_totals, bs, control)
                    baseline_scored += 1
                    line += f"  |  baseline {bs['supported']}/{bs['claims_checked']}"
                    entry["baseline"] = b_report
                    entry["baseline_drafts"] = control

            print(line)
            record.append(entry)

        print("\n" + "=" * 62)
        print("  GROUNDING REPORT")
        print("=" * 62)
        if skipped:
            print(f"\n  {len(skipped)} profile(s) could not be checked, and are excluded")
            print("  from every figure below rather than counted as ungrounded:")
            for name, err in skipped:
                print(f"    - {name}: {str(err)[:88]}")
        _print_totals("Multi-stage pipeline", pipeline_totals, scored)
        if args.baseline:
            _print_totals("Single-prompt baseline", baseline_totals, baseline_scored)
            p = pipeline_totals
            b = baseline_totals
            if p["claims"] and b["claims"]:
                p_rate = p["supported"] / p["claims"]
                b_rate = b["supported"] / b["claims"]
                delta = (p_rate - b_rate) * 100
                print(f"\n  Difference               {delta:+.1f} percentage points in favour of "
                      f"{'the pipeline' if delta >= 0 else 'the baseline'}")
                print(f"  Sample                   n={scored} profiles, "
                      f"{p['claims']} vs {b['claims']} claims")
                print("\n  Small sample. Quote the n alongside the percentage; this is a"
                      "\n  measurement on the profiles at hand, not a study.")

        if args.json_out:
            payload = {
                "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "profiles_scored": scored,
                "profiles_skipped": [{"name": n, "error": str(e)} for n, e in skipped],
                "pipeline_totals": pipeline_totals,
                "baseline_totals": baseline_totals if args.baseline else None,
                "per_profile": record,
            }
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            print(f"\n  Full per-claim record written to {args.json_out}")

        print()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
