from services.storage import get_connection


def get_dashboard_metrics() -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT attribution, confidence, status FROM content
            WHERE attribution IS NOT NULL AND attribution != 'pending'
            """
        ).fetchall()

        appeal_count = conn.execute(
            "SELECT COUNT(*) AS n FROM content WHERE status = 'under_review'"
        ).fetchone()["n"]

        verified_count = conn.execute(
            "SELECT COUNT(*) AS n FROM verified_creators"
        ).fetchone()["n"]

    total = len(rows)
    if total == 0:
        return {
            "total_submissions": 0,
            "likely_ai_count": 0,
            "likely_human_count": 0,
            "uncertain_count": 0,
            "likely_ai_pct": 0,
            "likely_human_pct": 0,
            "uncertain_pct": 0,
            "appeal_rate_pct": 0,
            "average_confidence": 0,
            "verified_creators": verified_count,
        }

    ai = sum(1 for r in rows if r["attribution"] == "likely_ai")
    human = sum(1 for r in rows if r["attribution"] == "likely_human")
    uncertain = sum(1 for r in rows if r["attribution"] == "uncertain")
    avg_conf = sum(r["confidence"] for r in rows) / total

    return {
        "total_submissions": total,
        "likely_ai_count": ai,
        "likely_human_count": human,
        "uncertain_count": uncertain,
        "likely_ai_pct": round(ai / total * 100, 1),
        "likely_human_pct": round(human / total * 100, 1),
        "uncertain_pct": round(uncertain / total * 100, 1),
        "appeal_rate_pct": round(appeal_count / total * 100, 1),
        "average_confidence": round(avg_conf, 3),
        "verified_creators": verified_count,
    }
