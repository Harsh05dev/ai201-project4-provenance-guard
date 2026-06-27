import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from services import audit
from services.labels import generate_label
from services.scoring import combine_signals
from services.storage import get_connection, init_db
from signals.llm_signal import analyze_llm
from signals.stylometric_signal import analyze_stylometric
from signals.transition_signal import analyze_transitions

app = Flask(__name__)


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _is_verified(creator_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM verified_creators WHERE creator_id = ?",
            (creator_id,),
        ).fetchone()
    return row is not None


@app.route("/")
def index():
    return jsonify(
        {
            "service": "Provenance Guard",
            "status": "running",
            "endpoints": {
                "POST /submit": "Submit text for attribution analysis",
                "POST /appeal": "Contest a classification (Milestone 5)",
                "POST /verify": "Earn verified human certificate (stretch)",
                "GET /log": "View audit log entries",
                "GET /dashboard": "Analytics dashboard (stretch)",
            },
            "note": "Use POST /submit with JSON body: {\"text\": \"...\", \"creator_id\": \"...\"}",
        }
    )


@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    creator_id = (data.get("creator_id") or "").strip()
    content_type = data.get("content_type", "text")

    if not text:
        return jsonify({"error": "text is required"}), 400
    if not creator_id:
        return jsonify({"error": "creator_id is required"}), 400

    content_id = str(uuid.uuid4())
    timestamp = _utc_now()

    llm_score = analyze_llm(text)
    stylometric_score = analyze_stylometric(text)
    transition_score = analyze_transitions(text)

    result = combine_signals(llm_score, stylometric_score, transition_score)
    confidence = result["confidence"]
    attribution = result["attribution"]
    verified = _is_verified(creator_id)
    label = generate_label(attribution, confidence, verified=verified)

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
                content_type,
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
        "content_type": content_type,
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": result["signals"]["llm_score"],
        "stylometric_score": result["signals"]["stylometric_score"],
        "transition_score": result["signals"]["transition_score"],
        "signal_spread": result["signal_spread"],
        "status": "classified",
    }
    audit.append_log(log_entry)

    return jsonify(
        {
            "content_id": content_id,
            "attribution": attribution,
            "confidence": confidence,
            "label": label,
            "signals": result["signals"],
            "verified_creator": verified,
        }
    )


@app.route("/log", methods=["GET"])
def get_log():
    limit = request.args.get("limit", 50, type=int)
    return jsonify({"entries": audit.get_recent_entries(limit=limit)})


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
