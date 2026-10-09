"""Lossless identifiers and conservative normalization of VSS evidence."""
from datetime import datetime, timezone
import hashlib
import math


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_id(value, prefix="asset"):
    return prefix + "-" + hashlib.sha256(str(value).encode()).hexdigest()[:16]


def number(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (ValueError, TypeError):
        return default


def provenance(row, source=None):
    return {
        "source_url": source or row.get("source") or row.get("source_uri") or row.get("original_video") or "",
        "captured_at": row.get("captured_at") or row.get("capture_timestamp") or None,
        "processed_at": row.get("processed_at") or utcnow(),
        "data_origin": "archive", "execution_mode": "real_provider", "freshness": "unknown",
        "notes": ["Indexed historical evidence; retrieval time does not establish capture time or current road conditions."],
    }


def timing(row):
    start = number(row.get("start_sec", row.get("segment_start_sec", row.get("start_time", 0))))
    end = number(row.get("end_sec", row.get("segment_end_sec", row.get("end_time", start + number(row.get("duration_sec", 0))))), start)
    return max(0, start), max(start, end)


def normalize_hit(row):
    source = row.get("source") or row.get("source_uri")
    original = row.get("original_video")
    start, end = timing(row)
    asset_id = stable_id(original or source)
    evidence_id = stable_id(f"{source}:{start}:{end}", "evidence")
    return {
        "id": evidence_id, "asset_id": asset_id, "evidence_id": evidence_id,
        "source_uri": source, "original_video": original,
        "start_sec": start, "end_sec": end,
        "summary": row.get("reasoning_content") or row.get("summary") or row.get("caption") or "No indexed description available.",
        "score": number(row.get("similarity_score", row.get("score", 0))),
        "camera_id": row.get("camera_id"), "location": row.get("location") or "Unlocated archive evidence",
        "provenance": provenance(row, source),
    }
