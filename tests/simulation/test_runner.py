import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest

from backend.errors import ProviderError
from backend.simulation import SimulationRunner, get_roads
from backend.simulation.runner import NETWORK_DIR, _aggregate_metrics, _binary, _metrics

SCENARIO = dict(name='Reproducibility check', network_id='nyc-demo-corridor', duration_sec=600, demand_vph=900, blockage_start_sec=60, early_clearance_sec=180, late_clearance_sec=420, seeds=[42])


class MetricsTests(unittest.TestCase):
    def test_completed_travel_time_weights_vehicles_and_accepts_zero_completion_seeds(self):
        runs = [
            {'seed': 1, 'throughput': 0, 'total_completed_travel_time_sec': 0, 'mean_completed_travel_time_sec': None},
            {'seed': 2, 'throughput': 2, 'total_completed_travel_time_sec': 20, 'mean_completed_travel_time_sec': 10},
            {'seed': 3, 'throughput': 1, 'total_completed_travel_time_sec': 30, 'mean_completed_travel_time_sec': 30},
        ]
        for ordered in (runs, list(reversed(runs))):
            result = _aggregate_metrics(ordered)
            self.assertEqual(result['mean_completed_travel_time_sec'], 16.67)
            self.assertEqual(result['throughput'], 1)
            self.assertEqual(len(result['per_seed']), 3)
        empty = _aggregate_metrics([runs[0], dict(runs[0], seed=4)])
        self.assertIsNone(empty['mean_completed_travel_time_sec'])
        self.assertEqual(empty['total_completed_travel_time_sec'], 0)

    def test_unfinished_and_backlog_cannot_disappear(self):
        with TemporaryDirectory() as folder:
            path = Path(folder)/'trip.xml'
            path.write_text('<tripinfos><tripinfo id="a" depart="3" arrival="15" duration="12" departDelay="3" waitingTime="2" timeLoss="1"/><tripinfo id="b" depart="8" arrival="-1" duration="12" departDelay="7" waitingTime="4" timeLoss="5"/></tripinfos>')
            metrics = _metrics(path, {'a':0,'b':1,'c':2}, 20, 2, 20)
            self.assertEqual(metrics['throughput'], 1)
            self.assertEqual(metrics['unfinished_vehicles'], 1)
            self.assertEqual(metrics['insertion_backlog'], 1)
            self.assertEqual(metrics['total_elapsed_journey_time_sec'], 52)
            self.assertEqual(metrics['total_waiting_time_sec'], 34)
            self.assertEqual(metrics['total_delay_sec'], 34)

    def test_invalid_scenario_rejected_before_runtime(self):
        with self.assertRaises(ProviderError) as caught:
            SimulationRunner(SimpleNamespace()).run(SCENARIO | {'late_clearance_sec':20}, 'bad', Event())
        self.assertEqual(caught.exception.code, 'invalid_scenario')

    def test_precancelled_run_never_starts(self):
        event = Event()
        event.set()
        with self.assertRaises(ProviderError) as caught:
            SimulationRunner(SimpleNamespace()).run(SCENARIO, 'cancel', event)
        self.assertEqual(caught.exception.code, 'simulation_cancelled')

    def test_missing_runtime_explicit(self):
        with self.assertRaises(ProviderError) as caught:
            _binary(SimpleNamespace(sumo_binary='definitely-no-sumo-binary'))
        self.assertEqual(caught.exception.code, 'sumo_unavailable')

    def test_versioned_osm_route_geometry_and_direction(self):
        roads = get_roads()
        manifest = json.loads((NETWORK_DIR/'manifest.json').read_text())
        self.assertGreaterEqual(len(roads), 5)
        self.assertTrue(manifest['validation']['contiguous_route'])
        self.assertTrue(manifest['validation']['passenger_lane_connections'])
        self.assertEqual([r['id'] for r in roads], ['osm-'+e for e in manifest['route_edges']])
        self.assertGreater(manifest['route_end_lonlat'][1], manifest['route_start_lonlat'][1])
        for road in roads:
            self.assertGreater(road['length_m'], 0)
            self.assertGreater(road['lanes'], 0)
            for lon,lat in road['geometry']['coordinates']:
                self.assertTrue(-74 < lon < -73.9 and 40.7 < lat < 40.8)


class ActualSUMOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.settings = SimpleNamespace(sumo_binary='sumo', output_dir=cls.temp.name, job_timeout_seconds=90)
        try:
            _binary(cls.settings)
        except ProviderError as exc:
            raise unittest.SkipTest(exc.message)
        cls.runner = SimulationRunner(cls.settings)
        cls.first = cls.runner.run(SCENARIO, 'first', Event())
        cls.second = cls.runner.run(SCENARIO, 'second', Event())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_deterministic_replay_and_metrics(self):
        for field in ('baseline','early','late','comparison','playback'):
            self.assertEqual(self.first[field], self.second[field])
        self.assertEqual(self.first['engine'], 'Eclipse SUMO sumo 1.27.1')
        self.assertEqual(self.first['execution_mode'], 'real_provider')
        self.assertEqual(self.first['data_origin'], 'synthetic')
        self.assertEqual(len(self.first['playback']['frames']), 61)

    def test_longer_blockage_increases_delay_and_preserves_demand(self):
        result = self.first
        self.assertGreater(result['late']['total_delay_sec'], result['early']['total_delay_sec'])
        self.assertLessEqual(result['late']['throughput'], result['early']['throughput'])
        for name in ('baseline','early','late'):
            m = result[name]
            self.assertEqual(m['scheduled_vehicles'], 150)
            self.assertEqual(m['scheduled_vehicles'], m['throughput']+m['unfinished_vehicles']+m['insertion_backlog'])

    def test_inflight_cancellation(self):
        event=Event()
        def progress(value):
            if value > .01:
                event.set()
        with self.assertRaises(ProviderError) as caught:
            self.runner.run(SCENARIO, 'interrupted', event, progress)
        self.assertEqual(caught.exception.code, 'simulation_cancelled')
        self.assertFalse((Path(self.temp.name)/'interrupted'/'result.json').exists())
