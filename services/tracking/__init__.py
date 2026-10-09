"""Conservative image-space association over timestamped detections only."""
from collections import defaultdict


def _iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2-x1) * max(0, y2-y1)
    union = (a[2]-a[0]) * (a[3]-a[1]) + (b[2]-b[0]) * (b[3]-b[1]) - inter
    return inter / union if union > 0 else 0


def associate(detections, *, max_gap_sec=1.0, minimum_iou=0.3):
    """Return tracks with at least two distinct timestamps. Never infer physical speed."""
    if len({d["timestamp_sec"] for d in detections}) < 2:
        return [], "unavailable: at least two timestamped detection frames are required"
    upstream = defaultdict(list)
    unassigned = []
    for d in sorted(detections, key=lambda d: (d["timestamp_sec"], d["id"])):
        if d.get("track_id") is not None:
            upstream[str(d["track_id"])].append(d)
        else:
            unassigned.append(d)
    tracks = [{"id": "upstream-" + key, "detection_ids": [d["id"] for d in group], "method": "upstream stable track identifier", "source": "upstream", "calibrated": False}
              for key, group in upstream.items() if len({d["timestamp_sec"] for d in group}) > 1]
    groups = []
    for d in unassigned:
        candidates = []
        for index, group in enumerate(groups):
            last = group[-1]
            dt = d["timestamp_sec"] - last["timestamp_sec"]
            if 0 < dt <= max_gap_sec and d["class_name"] == last["class_name"] and d["bbox_units"] == last["bbox_units"]:
                overlap = _iou(d["bbox"], last["bbox"])
                if overlap >= minimum_iou:
                    candidates.append((overlap, index))
        if candidates:
            groups[max(candidates)[1]].append(d)
        else:
            groups.append([d])
    for group in groups:
        if len(group) < 2:
            continue
        track_id = "image-iou-" + group[0]["id"]
        for d in group:
            d["track_id"] = track_id
        tracks.append({"id": track_id, "detection_ids": [d["id"] for d in group], "method": "application image-space IoU association (uncalibrated)", "source": "application", "calibrated": False})
    return tracks, "available" if tracks else "unavailable: no supported multi-frame associations"
