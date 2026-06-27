import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from services import audit
from services.storage import get_connection, init_db
from signals.llm_signal import analyze_llm

app = Flask(__name__)


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _placeholder_label():
    return "Classification pending full analysis pipeline."


@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    creator_id = (data.get("creator_id") or "").strip()

    if not text:
        return jsonify({"error": "text is required"}), 400
    if not creator_id:
        return jsonify({"error": "creator_id is required"}), 400

    content_id = str(uuid.uuid4())
    timestamp = _utc_now()

    llm_score = analyze_llm(text)
    confidence = llm_score  # placeholder until M4 ensemble scoring
    attribution = "pending"
    label = _placeholder_label()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO content
            (content_id, creator_id, text, content_type, attribution, confidence, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                content_id,
                creator_id,
                text,
                data.get("content_type", "text"),
                attribution,
                confidence,
                "classified",
                timestamp,
            ),
        )

    log_entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": timestamp,
        "attribution": attribution,
        "confidence": round(confidence, 4),
        "llm_score": round(llm_score, 4),
        "status": "classified",
    }
    audit.append_log(log_entry)

    return jsonify(
        {
            "content_id": content_id,
            "attribution": attribution,
            "confidence": round(confidence, 4),
            "label": label,
            "llm_score": round(llm_score, 4),
        }
    )


@app.route("/log", methods=["GET"])
def get_log():
    limit = request.args.get("limit", 50, type=int)
    return jsonify({"entries": audit.get_recent_entries(limit=limit)})


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
