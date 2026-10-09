"""Inspect sidecar capabilities; aggregated counts are not frame detections."""
import json
from backend.retrieval.normalize import number, stable_id
from services.tracking import associate


def normalize_detections(payload, evidence_id, start_sec=0):
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            payload = {}
    if not isinstance(payload, dict):
        return [], [], {"detections": "unavailable: unsupported sidecar schema", "tracking": "unavailable: temporal frames absent"}
    nested = payload.get("perception_json") or payload.get("sidecar")
    if nested:
        return normalize_detections(nested, evidence_id, start_sec)
    candidates = []
    frames = payload.get("frames", [])
    if isinstance(frames, list):
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            timestamp = frame.get("timestamp_sec", frame.get("time_sec", frame.get("timestamp")))
            for det in frame.get("detections", frame.get("objects", [])):
                if isinstance(det, dict):
                    candidates.append((det, timestamp, frame))
    for det in payload.get("detections", []):
        if isinstance(det, dict):
            candidates.append((det, det.get("timestamp_sec", det.get("time_sec")), payload))
    output = []
    for index, (det, timestamp, frame) in enumerate(candidates):
        if timestamp is None:
            # A frame index without a frame rate cannot supply an honest timestamp.
            continue
        stamp = number(timestamp, -1)
        box = det.get("bbox", det.get("xyxy"))
        if isinstance(box, dict):
            box = [box.get(k) for k in ("x1", "y1", "x2", "y2")]
        if not isinstance(box, (list, tuple)) or len(box) != 4 or stamp < 0:
            continue
        box = [number(v, -1) for v in box]
        if min(box) < 0 or box[2] <= box[0] or box[3] <= box[1]:
            continue
        units = det.get("bbox_units", frame.get("bbox_units", payload.get("bbox_units")))
        if units not in {"normalized", "pixels"}:
            units = "normalized" if max(box) <= 1 else "pixels"
        if units == "normalized" and max(box) > 1:
            continue
        class_name = det.get("class_name", det.get("label", det.get("class")))
        confidence = number(det.get("confidence", det.get("conf")), -1)
        if class_name is None or not 0 <= confidence <= 1:
            continue
        # videos/detections consumes a segment; local offsets are shifted to parent time.
        stamp += 0 if payload.get("time_reference") == "parent" else start_sec
        output.append({"id": stable_id(f"{evidence_id}:{index}:{stamp}", "detection"), "evidence_id": evidence_id,
                       "class_name": str(class_name), "confidence": confidence, "timestamp_sec": stamp,
                       "bbox": box, "bbox_units": units, "track_id": str(det["track_id"]) if det.get("track_id") is not None else None,
                       "model": payload.get("model") or "YOLO11 (pipeline sidecar)", "execution_mode": "real_provider"})
    tracks, tracking = associate(output)
    return output, tracks, {"detections": "available" if output else "unavailable: no supported timestamped bounding boxes", "tracking": tracking}
