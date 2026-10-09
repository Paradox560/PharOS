"""Detector coordinate and temporal evidence regression tests."""
import json
from pathlib import Path
import unittest

from backend.inference.detections import normalize_detections
from services.tracking import associate


def temporal_sidecar(track_id=None):
    frames = []
    for timestamp in (0, .2):
        detection = {'class_name': 'car', 'confidence': .91, 'bbox': [.1, .2, .4, .6], 'bbox_units': 'normalized'}
        if track_id is not None:
            detection['track_id'] = track_id
        frames.append({'time_sec': timestamp, 'detections': [detection]})
    return {'frames': frames}


class ScopedTrackTests(unittest.TestCase):
    def test_upstream_track_ids_are_scoped_to_segment_evidence(self):
        first_detections, first_tracks, _ = normalize_detections(temporal_sidecar(1), 'segment-A')
        second_detections, second_tracks, _ = normalize_detections(temporal_sidecar(1), 'segment-B')
        self.assertEqual(len(first_tracks), 1)
        self.assertEqual(len(second_tracks), 1)
        self.assertNotEqual(first_tracks[0]['id'], second_tracks[0]['id'])
        self.assertEqual(first_tracks[0]['upstream_track_id'], '1')
        self.assertTrue(all(d['track_id'] == first_tracks[0]['id'] for d in first_detections))
        self.assertTrue(all(d['track_id'] == second_tracks[0]['id'] for d in second_detections))
        self.assertTrue(all(d['upstream_track_id'] == '1' for d in first_detections))

    def test_single_frame_upstream_identifier_does_not_establish_a_track(self):
        payload = temporal_sidecar(1)
        payload['frames'] = payload['frames'][:1]
        detections, tracks, availability = normalize_detections(payload, 'segment')
        self.assertEqual(tracks, [])
        self.assertIsNone(detections[0]['track_id'])
        self.assertEqual(detections[0]['upstream_track_id'], '1')
        self.assertIn('unavailable', availability['tracking'])

    def test_application_association_never_crosses_evidence_segments(self):
        a, _, _ = normalize_detections({'frames': temporal_sidecar()['frames'][:1]}, 'segment-A')
        b, _, _ = normalize_detections({'frames': temporal_sidecar()['frames'][1:]}, 'segment-B')
        tracks, availability = associate(a + b)
        self.assertEqual(tracks, [])
        self.assertIn('unavailable', availability)


class CoordinateTests(unittest.TestCase):
    def test_real_adjacent_team8_frames_produce_application_tracks(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/team8_i24_first_three_frames.json').read_text())
        payload = fixture['sidecar']
        self.assertEqual([len(frame['detections']) for frame in payload['frames']], [11, 14, 14])
        self.assertEqual([frame['time_sec'] for frame in payload['frames']], [0, .0333, .0667])
        detections, tracks, status = normalize_detections(payload, 'i24-live-segment-6', fixture['provenance']['parent_start_sec'])
        self.assertEqual(len(detections), 39)
        self.assertEqual(len(tracks), 13)
        self.assertEqual(status, {'detections': 'available', 'tracking': 'available'})
        self.assertTrue(all(t['source'] == 'application' and t['calibrated'] is False for t in tracks))
        self.assertTrue(all(d.get('upstream_track_id') is None for d in detections))
        self.assertTrue(all(d['bbox_units'] == 'normalized' and all(0 <= value <= 1 for value in d['bbox']) for d in detections))
        # Follow an observed car across all three adjacent frames, keeping parent time.
        first_car_track = detections[0]['track_id']
        self.assertIsNotNone(first_car_track)
        car = [d for d in detections if d['track_id'] == first_car_track]
        self.assertEqual([d['timestamp_sec'] for d in car], [25, 25.0333, 25.0667])
        self.assertEqual([d['source_bbox'] for d in car], [
            [1364, 797, 1455, 865], [1351, 786, 1445, 852], [1341, 775, 1433, 841]])
        self.assertTrue(all(d['class_name'] == 'car' for d in car))
        self.assertTrue(all(d['source_frame_width'] == 1920 and d['source_frame_height'] == 1080 for d in car))

    def test_live_team8_car_sample_uses_shape_and_segment_offset(self):
        # Read-only Team 8 probe, 2026-10-09T16:31:34Z, i24_cam-1 segment 6.
        # This retains one observed object only; it cannot establish a track.
        payload = {'source': 'yolo11_coco', 'frames': [
            {'frame_index': 0, 'time_sec': 0, 'shape': [1080, 1920], 'detections': [
                {'label': 'car', 'confidence': .7349, 'bbox': [1364, 797, 1455, 865]}]}]}
        detections, tracks, _ = normalize_detections(payload, 'i24-segment-6', 25)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0]['class_name'], 'car')
        self.assertEqual(detections[0]['timestamp_sec'], 25)
        self.assertEqual(detections[0]['bbox'], [1364/1920, 797/1080, 1455/1920, 865/1080])
        self.assertEqual(detections[0]['bbox_units'], 'normalized')
        self.assertEqual(detections[0]['model'], 'yolo11_coco')
        self.assertIsNone(detections[0]['track_id'])
        self.assertEqual(tracks, [])

    def test_workshop_height_width_shape_normalizes_inference_pixels(self):
        # Inference is 640x360; parent playback can be 1920x1080 without changing overlay.
        payload = {'source': 'yolo11_coco', 'video_shape': [1080, 1920], 'frames': [
            {'frame_index': 0, 'time_sec': 0, 'shape': [360, 640], 'detections': [
                {'label': 'car', 'confidence': .91, 'bbox': [64, 72, 320, 180]}]}]}
        detections, tracks, _ = normalize_detections(payload, 'segment', 20)
        self.assertEqual(detections[0]['bbox'], [.1, .2, .5, .5])
        self.assertEqual(detections[0]['bbox_units'], 'normalized')
        self.assertEqual(detections[0]['source_frame_width'], 640)
        self.assertEqual(detections[0]['source_frame_height'], 360)
        self.assertEqual(detections[0]['source_bbox'], [64, 72, 320, 180])
        self.assertEqual(detections[0]['timestamp_sec'], 20)
        self.assertEqual(detections[0]['model'], 'yolo11_coco')
        self.assertEqual(tracks, [])

    def test_video_shape_and_explicit_dimensions_supported(self):
        for size in ({'video_shape': [360, 640]}, {'width': 640, 'height': 360}):
            payload = size | {'detections': [{'time_sec': .5, 'label': 'car', 'confidence': .9, 'bbox': [64, 72, 320, 180]}]}
            detections, _, _ = normalize_detections(payload, 'e')
            self.assertEqual(detections[0]['bbox'], [.1, .2, .5, .5])

    def test_pixel_dimensions_are_not_guessed_from_playback_or_box_magnitude(self):
        for bbox in ([64, 72, 320, 180], [.1, .2, .5, .5]):
            payload = {'frames': [{'time_sec': 0, 'detections': [{'label': 'car', 'confidence': .9, 'bbox': bbox}]}]}
            detections, tracks, status = normalize_detections(payload, 'e')
            self.assertEqual(detections, [])
            self.assertEqual(tracks, [])
            self.assertIn('dimensions', status['detections'])

    def test_bad_per_frame_dimensions_do_not_fall_back_to_different_video_size(self):
        for size in ({'shape': [-1, 640]}, {'shape': {'width': 640, 'height': -1}}, {'width': 640, 'height': -1}):
            payload = {'video_shape': [1080, 1920], 'frames': [size | {'time_sec': 0,
                       'detections': [{'label': 'car', 'confidence': .9, 'bbox': [64, 72, 320, 180]}]}]}
            detections, _, status = normalize_detections(payload, 'e')
            self.assertEqual(detections, [])
            self.assertIn('dimensions', status['detections'])

    def test_temporal_frames_take_precedence_over_aggregate_perception_json(self):
        payload = temporal_sidecar()
        payload['perception_json'] = '{"object_counts":{"car":1}}'
        detections, tracks, _ = normalize_detections(payload, 'e')
        self.assertEqual(len(detections), 2)
        self.assertEqual(len(tracks), 1)
