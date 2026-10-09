"""Inspect sidecar capabilities; aggregated counts are not frame detections.

Workshop pixel boxes use each inference frame's [height, width] shape. This order
is defined by the official VSS frontend's bboxSourceSize, not playback dimensions.
"""
import json
from backend.retrieval.normalize import number, stable_id
from services.tracking import associate


def _dimensions(frame, payload):
    for source, shape_key in ((frame, 'shape'), (payload, 'video_shape')):
        width, height = number(source.get('width'), -1), number(source.get('height'), -1)
        if width > 0 and height > 0:
            return width, height
        if 'width' in source or 'height' in source:
            return None
        shape = source.get(shape_key)
        if isinstance(shape, dict):
            width, height = number(shape.get('width'), -1), number(shape.get('height'), -1)
            if width > 0 and height > 0:
                return width, height
        if isinstance(shape, (list, tuple)) and len(shape) >= 2:
            # Verified VSS Blueprint detection-overlay.util.ts: h=shape[0], w=shape[1].
            height, width = number(shape[0], -1), number(shape[1], -1)
            if width > 0 and height > 0:
                return width, height
        if shape is not None:
            return None  # An invalid per-frame shape cannot be replaced by a guessed size.
    return None


def normalize_detections(payload, evidence_id, start_sec=0):
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            payload = {}
    if not isinstance(payload, dict):
        return [], [], {"detections": "unavailable: unsupported sidecar schema", "tracking": "unavailable: temporal frames absent"}
    nested = payload.get("perception_json") or payload.get("sidecar")
    if nested and not payload.get('frames'):
        return normalize_detections(nested, evidence_id, start_sec)
    candidates = []
    frames = payload.get("frames", [])
    if isinstance(frames, list):
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            timestamp = frame.get("timestamp_sec", frame.get("time_sec", frame.get("timestamp")))
            frame_detections = frame.get("detections", frame.get("objects", []))
            for det in frame_detections if isinstance(frame_detections, list) else []:
                if isinstance(det, dict):
                    candidates.append((det, timestamp, frame))
    flat_detections = payload.get("detections", [])
    for det in flat_detections if isinstance(flat_detections, list) else []:
        if isinstance(det, dict):
            candidates.append((det, det.get("timestamp_sec", det.get("time_sec")), payload))
    output = []
    unavailable_coordinates = False
    for index, (det, timestamp, frame) in enumerate(candidates):
        if timestamp is None:
            # A frame index without a verified time mapping cannot supply an honest timestamp.
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
        dimensions = _dimensions(frame, payload)
        units = det.get("bbox_units", frame.get("bbox_units", payload.get("bbox_units")))
        if units not in {"normalized", "pixels"}:
            # Workshop bboxes are pixel xyxy. Never infer normalized units from small numbers.
            units = 'pixels'
        source_box = list(box)
        if units == 'pixels':
            if dimensions is None:
                unavailable_coordinates = True
                continue
            width, height = dimensions
            if box[2] > width or box[3] > height:
                unavailable_coordinates = True
                continue
            box = [box[0]/width, box[1]/height, box[2]/width, box[3]/height]
        elif max(box) > 1:
            continue
        class_name = det.get("class_name", det.get("label", det.get("class")))
        confidence = number(det.get("confidence", det.get("conf")), -1)
        if class_name is None or not 0 <= confidence <= 1:
            continue
        # videos/detections consumes a segment; local offsets are shifted to parent time.
        stamp += 0 if payload.get("time_reference") == "parent" else start_sec
        detection = {"id": stable_id(f"{evidence_id}:{index}:{stamp}", "detection"), "evidence_id": evidence_id,
                     "class_name": str(class_name), "confidence": confidence, "timestamp_sec": stamp,
                     "bbox": box, "bbox_units": "normalized", "track_id": str(det["track_id"]) if det.get("track_id") is not None else None,
                     "model": payload.get("model") or (payload.get('source') if str(payload.get('source', '')).startswith('yolo') else None) or "YOLO11 (pipeline sidecar)", "execution_mode": "real_provider",
                     'source_bbox': source_box, 'source_bbox_units': units}
        if dimensions:
            detection['source_frame_width'], detection['source_frame_height'] = dimensions
        output.append(detection)
    tracks, tracking = associate(output)
    unavailable = 'unavailable: bounding-box frame dimensions are missing or inconsistent' if unavailable_coordinates else 'unavailable: no supported timestamped bounding boxes'
    return output, tracks, {"detections": "available" if output else unavailable, "tracking": tracking}
