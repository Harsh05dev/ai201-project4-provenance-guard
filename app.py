import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template_string, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from services import audit
from services.analytics import get_dashboard_metrics
from services.content import get_content, normalize_submission_text, update_content_status
from services.labels import generate_label
from services.scoring import combine_signals
from services.storage import get_connection, init_db
from signals.llm_signal import analyze_llm
from signals.stylometric_signal import analyze_stylometric
from signals.transition_signal import analyze_transitions

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _is_verified(creator_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM verified_creators WHERE creator_id = ?",
            (creator_id,),
        ).fetchone()
    return row is not None


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Provenance Guard</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; color: #1a1a1a; }
    h1 { color: #2563eb; }
    code { background: #f1f5f9; padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.9em; }
    pre { background: #0f172a; color: #e2e8f0; padding: 1rem; border-radius: 8px; overflow-x: auto; font-size: 0.85em; }
    a { color: #2563eb; }
    .badge { display: inline-block; background: #dcfce7; color: #166534; padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.85em; }
    ul { padding-left: 1.25rem; }
  </style>
</head>
<body>
  <h1>Provenance Guard</h1>
  <p><span class="badge">running</span> Attribution analysis API for creative content.</p>
  <h2>Endpoints</h2>
  <ul>
    <li><code>POST /submit</code> — Submit text for AI/human classification</li>
    <li><code>POST /appeal</code> — Contest a classification</li>
    <li><code>POST /verify</code> — Earn verified human certificate</li>
    <li><a href="/log">GET /log</a> — View audit log (JSON)</li>
    <li><a href="/dashboard">GET /dashboard</a> — Analytics dashboard</li>
  </ul>
  <h2>Try a submission</h2>
  <pre>curl -X POST http://127.0.0.1:5000/submit \\
  -H "Content-Type: application/json" \\
  -d '{"text": "Your text here...", "creator_id": "your-name"}'</pre>
  <p><a href="/?format=json">View API info as JSON</a></p>
</body>
</html>"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Provenance Guard — Dashboard</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
    h1 { color: #2563eb; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin: 1.5rem 0; }
    .card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 1rem; }
    .card h3 { margin: 0 0 0.25rem; font-size: 0.85rem; color: #64748b; text-transform: uppercase; }
    .card .value { font-size: 1.75rem; font-weight: 700; color: #0f172a; }
    .bar { height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden; margin-top: 0.5rem; }
    .bar-fill { height: 100%; }
    .ai { background: #ef4444; }
    .human { background: #22c55e; }
    .uncertain { background: #f59e0b; }
    a { color: #2563eb; }
  </style>
</head>
<body>
  <h1>Analytics Dashboard</h1>
  <p><a href="/">← Back to home</a></p>
  <div class="grid">
    <div class="card"><h3>Total Submissions</h3><div class="value">{{ total_submissions }}</div></div>
    <div class="card"><h3>Appeal Rate</h3><div class="value">{{ appeal_rate_pct }}%</div></div>
    <div class="card"><h3>Avg Confidence</h3><div class="value">{{ average_confidence }}</div></div>
    <div class="card"><h3>Verified Creators</h3><div class="value">{{ verified_creators }}</div></div>
  </div>
  <h2>Detection Patterns</h2>
  <div class="grid">
    <div class="card">
      <h3>Likely AI</h3>
      <div class="value">{{ likely_ai_count }} ({{ likely_ai_pct }}%)</div>
      <div class="bar"><div class="bar-fill ai" style="width: {{ likely_ai_pct }}%"></div></div>
    </div>
    <div class="card">
      <h3>Likely Human</h3>
      <div class="value">{{ likely_human_count }} ({{ likely_human_pct }}%)</div>
      <div class="bar"><div class="bar-fill human" style="width: {{ likely_human_pct }}%"></div></div>
    </div>
    <div class="card">
      <h3>Uncertain</h3>
      <div class="value">{{ uncertain_count }} ({{ uncertain_pct }}%)</div>
      <div class="bar"><div class="bar-fill uncertain" style="width: {{ uncertain_pct }}%"></div></div>
    </div>
  </div>
</body>
</html>"""


@app.route("/")
def index():
    if request.args.get("format") == "json":
        return jsonify(
            {
                "service": "Provenance Guard",
                "status": "running",
                "endpoints": {
                    "POST /submit": "Submit text for attribution analysis",
                    "POST /appeal": "Contest a classification",
                    "POST /verify": "Earn verified human certificate",
                    "GET /log": "View audit log entries",
                    "GET /dashboard": "Analytics dashboard",
                },
            }
        )
    return render_template_string(INDEX_HTML)


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    data = request.get_json(silent=True) or {}
    creator_id = (data.get("creator_id") or "").strip()
    content_type = data.get("content_type", "text")

    if not creator_id:
        return jsonify({"error": "creator_id is required"}), 400

    text, error = normalize_submission_text(data)
    if error:
        return jsonify({"error": error}), 400

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
            "content_type": content_type,
            "attribution": attribution,
            "confidence": confidence,
            "label": label,
            "signals": result["signals"],
            "verified_creator": verified,
        }
    )


@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json(silent=True) or {}
    content_id = (data.get("content_id") or "").strip()
    creator_reasoning = (data.get("creator_reasoning") or "").strip()

    if not content_id:
        return jsonify({"error": "content_id is required"}), 400
    if len(creator_reasoning) < 10:
        return jsonify({"error": "creator_reasoning must be at least 10 characters"}), 400

    content = get_content(content_id)
    if not content:
        return jsonify({"error": "content not found"}), 404
    if content["status"] == "under_review":
        return jsonify({"error": "appeal already submitted for this content"}), 409

    timestamp = _utc_now()
    update_content_status(content_id, "under_review")

    log_entry = {
        "content_id": content_id,
        "creator_id": content["creator_id"],
        "timestamp": timestamp,
        "event": "appeal_filed",
        "attribution": content["attribution"],
        "confidence": content["confidence"],
        "original_attribution": content["attribution"],
        "original_confidence": content["confidence"],
        "appeal_reasoning": creator_reasoning,
        "status": "under_review",
    }
    audit.append_log(log_entry, event_type="appeal")

    return jsonify(
        {
            "content_id": content_id,
            "status": "under_review",
            "message": "Appeal received. Your content is now under review by our team.",
        }
    )


@app.route("/verify", methods=["POST"])
def verify():
    data = request.get_json(silent=True) or {}
    creator_id = (data.get("creator_id") or "").strip()
    attestation_phrase = (data.get("attestation_phrase") or "").strip()

    if not creator_id:
        return jsonify({"error": "creator_id is required"}), 400
    if not attestation_phrase:
        return jsonify({"error": "attestation_phrase is required"}), 400

    words = attestation_phrase.split()
    if len(words) < 20:
        return jsonify({"error": "attestation_phrase must be at least 20 words"}), 400

    lower = attestation_phrase.lower()
    if not any(p in lower for p in (" i ", " my ", " me ", "i'm", "i've")):
        if not lower.startswith("i ") and " i " not in f" {lower} ":
            return jsonify(
                {"error": "attestation must include first-person language (I, my, me)"}
            ), 400

    if _is_verified(creator_id):
        return jsonify(
            {
                "creator_id": creator_id,
                "status": "already_verified",
                "message": "Creator already holds a verified human certificate.",
            }
        )

    timestamp = _utc_now()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO verified_creators (creator_id, verified_at) VALUES (?, ?)",
            (creator_id, timestamp),
        )

    audit.append_log(
        {
            "creator_id": creator_id,
            "timestamp": timestamp,
            "event": "verification_granted",
            "status": "verified_human",
        },
        event_type="verification",
    )

    return jsonify(
        {
            "creator_id": creator_id,
            "status": "verified_human",
            "message": "Verification complete. Future submissions will display a verified creator badge.",
        }
    )


@app.route("/dashboard")
def dashboard():
    metrics = get_dashboard_metrics()
    if request.args.get("format") == "json":
        return jsonify(metrics)
    return render_template_string(DASHBOARD_HTML, **metrics)


@app.route("/log", methods=["GET"])
def get_log():
    limit = request.args.get("limit", 50, type=int)
    return jsonify({"entries": audit.get_recent_entries(limit=limit)})


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
