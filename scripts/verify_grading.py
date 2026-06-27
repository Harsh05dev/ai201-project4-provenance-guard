#!/usr/bin/env python3
"""Run: python scripts/verify_grading.py — checks all 29+4 rubric criteria."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app

PASS = FAIL = 0
checks = []


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        checks.append(("PASS", name, detail))
    else:
        FAIL += 1
        checks.append(("FAIL", name, detail))


def main():
    c = app.test_client()

    ai_text = (
        "Artificial intelligence represents a transformative paradigm shift in modern society. "
        "It is important to note that while the benefits of AI are numerous, it is equally essential "
        "to consider the ethical implications. Furthermore, stakeholders across various sectors "
        "must collaborate to ensure responsible deployment."
    )
    human_text = (
        "ok so i finally tried that new ramen place downtown and honestly? underwhelming. "
        "the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after."
    )
    uncertain_text = (
        "Remote work has changed how teams collaborate. Additionally, many companies are adopting "
        "hybrid models. I think the future will blend office and home time in ways we are still figuring out."
    )

    r_ai = c.post("/submit", json={"text": ai_text, "creator_id": "verify-ai"})
    r_human = c.post("/submit", json={"text": human_text, "creator_id": "verify-human"})
    r_unc = c.post("/submit", json={"text": uncertain_text, "creator_id": "verify-unc"})

    ai = r_ai.get_json() or {}
    human = r_human.get_json() or {}
    unc = r_unc.get_json() or {}

    # Content Submission Endpoint (3pts)
    check("Submit returns structured JSON", r_ai.status_code == 200 and "content_id" in ai)
    check("Response includes attribution", ai.get("attribution") in ("likely_ai", "likely_human", "uncertain"))
    check("Response includes confidence score", isinstance(ai.get("confidence"), (int, float)))
    check("Response includes label text", isinstance(ai.get("label"), str) and len(ai.get("label", "")) > 30)

    # Multi-Signal Pipeline (2pts)
    check("Individual signal scores in response", all(k in ai.get("signals", {}) for k in ("llm_score", "stylometric_score", "transition_score")))

    # Confidence Scoring (2pts)
    check("AI vs human scores differ meaningfully", abs(ai["confidence"] - human["confidence"]) > 0.15,
          f"ai={ai.get('confidence')} human={human.get('confidence')}")

    # Transparency Label (3pts) — verified via code + README; live check labels differ
    check("AI and human labels use different text", ai.get("label") != human.get("label"))
    check("Uncertain attribution reachable", unc.get("attribution") == "uncertain", f"got {unc.get('attribution')}")

    # Appeals (2pts)
    cid = human.get("content_id")
    r_appeal = c.post("/appeal", json={
        "content_id": cid,
        "creator_reasoning": "I wrote this review myself after eating at the restaurant.",
    })
    appeal = r_appeal.get_json() or {}
    check("Appeal accepted with reasoning", r_appeal.status_code == 200 and appeal.get("status") == "under_review")

    log = c.get("/log").get_json().get("entries", [])
    appeal_entries = [e for e in log if e.get("event") == "appeal_filed" or e.get("status") == "under_review"]
    check("Appeal visible in audit log", len(appeal_entries) > 0)
    if appeal_entries:
        ae = appeal_entries[0]
        check("Appeal log has status under_review", ae.get("status") == "under_review")
        check("Appeal log has creator reasoning", "appeal_reasoning" in ae)

    # Audit Log (3pts)
    classified = [e for e in log if e.get("attribution") and e.get("attribution") != "pending"]
    check("Audit log has 3+ entries", len(classified) >= 3, f"count={len(classified)}")
    if classified:
        e0 = classified[0]
        check("Log entry has timestamp", "timestamp" in e0)
        check("Log entry has attribution", "attribution" in e0)
        check("Log entry has confidence", "confidence" in e0)

    # Stretch: Verify certificate
    phrase = (
        "I am writing this attestation to confirm that I am a real human creator and I personally "
        "authored all of my submissions on this platform using my own words and experiences from my life."
    )
    c.post("/verify", json={"creator_id": "verify-human", "attestation_phrase": phrase})
    r_ver = c.post("/submit", json={"text": "I walked my dog in the park yesterday.", "creator_id": "verify-human"})
    ver = r_ver.get_json() or {}
    check("Verified label distinguishable", ver.get("label", "").startswith("[Verified Creator]"))

    # Stretch: Multi-modal
    r_meta = c.post("/submit", json={
        "content_type": "metadata",
        "creator_id": "verify-meta",
        "metadata": {"title": "Sunset", "bio": "I took this photo", "tags": ["nature"]},
    })
    meta = r_meta.get_json() or {}
    check("Metadata submission works", r_meta.status_code == 200 and "attribution" in meta)

    r_img = c.post("/submit", json={
        "content_type": "image_description",
        "creator_id": "verify-img",
        "text": "A cat sleeping on a windowsill in afternoon sunlight",
    })
    check("Image description submission works", r_img.status_code == 200)

    # Stretch: Dashboard
    dash = c.get("/dashboard?format=json").get_json() or {}
    check("Dashboard has detection pattern metrics", "likely_ai_pct" in dash and "likely_human_pct" in dash)
    check("Dashboard has appeal rate", "appeal_rate_pct" in dash)
    check("Dashboard has extra metric", "average_confidence" in dash)

    # Rate limit in subprocess (fresh limiter memory)
    root = ROOT
    rl_out = subprocess.check_output(
        [sys.executable, "-c", """
from app import app
c = app.test_client()
codes = [c.post("/submit", json={"text": f"rl{i}", "creator_id": "rl"}).status_code for i in range(12)]
print(",".join(map(str, codes)))
"""],
        cwd=root,
        text=True,
    ).strip()
    codes = [int(x) for x in rl_out.split(",")]
    check("Rate limit: 10x200 then 429", codes[:10] == [200] * 10 and 429 in codes[10:],
          str(codes))

    print("\n=== GRADING VERIFICATION ===\n")
    for status, name, detail in checks:
        line = f"[{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print(f"\nTotal: {PASS} passed, {FAIL} failed out of {PASS + FAIL} automated checks")
    print("\nManual/doc checks (verify in README + planning.md):")
    print("  [doc] README: 3 label variants written out")
    print("  [doc] README: rate limit limits + reasoning")
    print("  [doc] README: known limitations tied to signals")
    print("  [doc] README: spec reflection + AI usage (2+ instances with revisions)")
    print("  [doc] planning.md: signals, thresholds, labels, appeals, edge cases, AI Tool Plan")
    print("  [manual] Portfolio walkthrough video recorded")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
