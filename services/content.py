from services.storage import get_connection

VALID_CONTENT_TYPES = {"text", "image_description", "metadata"}


def normalize_submission_text(data: dict) -> tuple[str | None, str | None]:
    """Return (text_to_analyze, error_message)."""
    content_type = data.get("content_type", "text")
    if content_type not in VALID_CONTENT_TYPES:
        return None, f"content_type must be one of: {', '.join(sorted(VALID_CONTENT_TYPES))}"

    if content_type == "metadata":
        metadata = data.get("metadata")
        if not metadata or not isinstance(metadata, dict):
            return None, "metadata object is required when content_type is metadata"
        parts = []
        for key in ("title", "bio", "tags", "description"):
            value = metadata.get(key)
            if value is None:
                continue
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            parts.append(f"{key}: {value}")
        if not parts:
            return None, "metadata must include at least one of: title, bio, tags, description"
        return "\n".join(parts), None

    text = (data.get("text") or "").strip()
    if not text:
        field = "text" if content_type == "text" else "text (image description)"
        return None, f"{field} is required for content_type '{content_type}'"
    return text, None


def get_content(content_id: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM content WHERE content_id = ?",
            (content_id,),
        ).fetchone()
    return dict(row) if row else None


def update_content_status(content_id: str, status: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE content SET status = ? WHERE content_id = ?",
            (status, content_id),
        )
