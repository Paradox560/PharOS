"""Bounded SUMO/TraCI comparisons over an attributed OSM network."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
import signal
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET

from backend.errors import ProviderError
from backend.models import SimulationScenario
from backend.retrieval.normalize import utcnow

NETWORK_DIR = Path(__file__).resolve().parents[2] / 'simulation' / 'networks'


def get_roads():
    path = NETWORK_DIR/'roads.json'
    return json.loads(path.read_text()) if path.exists() else []


def _binary(settings):
    configured = getattr(settings, 'sumo_binary', 'sumo')
    candidate = shutil.which(configured)
    if configured == 'sumo':
        try:
            import sumo
            native = Path(sumo.__file__).parent / 'bin' / 'sumo'
            if native.is_file():
                candidate = str(native)
        except ImportError:
            pass
    if not candidate:
        local = Path(sys.executable).parent / configured
        if local.is_file():
            candidate = str(local)
    if not candidate:
        raise ProviderError('sumo_unavailable', 'SUMO runtime is not installed. Install the pinned simulation dependencies.')
    try:
        checked = subprocess.run([candidate, '--version'], capture_output=True, text=True, timeout=10)
        if checked.returncode:
            raise ValueError
        version = checked.stdout.splitlines()[0]
    except (OSError, subprocess.SubprocessError, ValueError):
        raise ProviderError('sumo_unavailable', 'SUMO runtime could not start. Check its native runtime dependencies.') from None
    return candidate, version


def _metrics(trip_path, scheduled, duration, peak_queue, queue_sum):
    rows = {row.get('id'): row.attrib for row in ET.parse(trip_path).getroot().findall('tripinfo')}
    complete = [r for r in rows.values() if float(r.get('arrival', '-1')) >= 0]
    departed = {key: r for key, r in rows.items() if float(r.get('depart', '-1')) >= 0}
    unfinished = len(departed) - len(complete)
    pending = len(scheduled) - len(departed)
    accrued, waiting, delay = 0.0, 0.0, 0.0
    for vehicle, planned in scheduled.items():
        row = departed.get(vehicle)
        if row:
            arrival = float(row.get('arrival', '-1'))
            accrued += (arrival if arrival >= 0 else duration) - planned
            insertion = float(row.get('departDelay', '0'))
            waiting += float(row.get('waitingTime', '0')) + insertion
            delay += float(row.get('timeLoss', '0')) + insertion
        else:
            backlog = max(0, duration-planned)
            accrued += backlog
            waiting += backlog
            delay += backlog
    completed_duration = sum(float(r['duration']) for r in complete)
    return {
        'scheduled_vehicles': len(scheduled), 'departed_vehicles': len(departed), 'throughput': len(complete),
        'unfinished_vehicles': unfinished, 'insertion_backlog': pending,
        'completion_rate': round(len(complete)/max(1,len(scheduled)), 4),
        'total_completed_travel_time_sec': round(completed_duration, 2),
        'mean_completed_travel_time_sec': round(completed_duration/len(complete), 2) if complete else None,
        'mean_elapsed_journey_time_sec': round(accrued/max(1,len(scheduled)), 2),
        'total_elapsed_journey_time_sec': round(accrued, 2),
        'total_waiting_time_sec': round(waiting, 2), 'total_delay_sec': round(delay, 2),
        'mean_delay_sec': round(delay/max(1,len(scheduled)), 2),
        'peak_queue_vehicles': peak_queue, 'mean_queue_vehicles': round(queue_sum/duration, 2),
        'metric_note': 'Elapsed journey time includes unfinished and not-yet-inserted vehicles and is a censored lower bound; completed travel time excludes unfinished vehicles. Waiting/delay include insertion backlog.',
    }


def _aggregate_metrics(runs):
    """Average paired-seed totals; weight completed journey duration by vehicles."""
    aggregate = {}
    for key, value in runs[0].items():
        if key in {'seed', 'mean_completed_travel_time_sec'}:
            continue
        aggregate[key] = round(sum(row[key] for row in runs)/len(runs), 2) if isinstance(value, (int, float)) else value
    completed_count = sum(row['throughput'] for row in runs)
    completed_duration = sum(row['total_completed_travel_time_sec'] for row in runs)
    aggregate['mean_completed_travel_time_sec'] = round(completed_duration/completed_count, 2) if completed_count else None
    aggregate['completed_travel_time_aggregation'] = 'Sum of completed vehicle journey durations divided by all completed vehicles across paired seeds; null if none completed.'
    aggregate['per_seed'] = runs
    return aggregate


class SimulationRunner:
    def __init__(self, settings):
        self.settings = settings

    def run(self, scenario: dict, run_id: str, cancel_event: threading.Event, progress=lambda value: None):
        try:
            inputs = SimulationScenario.model_validate(deepcopy(scenario)).model_dump()
        except Exception:
            raise ProviderError('invalid_scenario', 'Scenario timing, demand, duration, or seeds are invalid.', 422) from None
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', run_id):
            raise ProviderError('invalid_run_id', 'Simulation run identifier is invalid.', 422)
        if cancel_event.is_set():
            raise ProviderError('simulation_cancelled', 'Simulation was cancelled.', 409)
        binary, version = _binary(self.settings)
        try:
            import traci
        except ImportError:
            raise ProviderError('sumo_unavailable', 'The pinned TraCI runtime is not installed.') from None
        manifest_path = NETWORK_DIR/'manifest.json'
        if not manifest_path.exists() or not (NETWORK_DIR/'nyc-demo-corridor.net.xml.gz').exists():
            raise ProviderError('sumo_network_unavailable', 'The versioned OSM corridor network is unavailable.')
        manifest = json.loads(manifest_path.read_text())
        run_dir = Path(self.settings.output_dir)/run_id
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            raise ProviderError('simulation_exists', 'Simulation output already exists for this immutable run identifier.', 409) from None
        (run_dir/'scenario.json').write_text(json.dumps(inputs, indent=2))
        route_edges = manifest['route_edges']
        scheduled = {f'veh-{i:05d}': round(i*3600/inputs['demand_vph'], 4) for i in range(math.ceil(inputs['duration_sec']*inputs['demand_vph']/3600)) if i*3600/inputs['demand_vph'] < inputs['duration_sec']}
        routes = ET.Element('routes')
        ET.SubElement(routes, 'vType', id='passenger', vClass='passenger', accel='2.6', decel='4.5', sigma='0.5', length='5', minGap='2.5', maxSpeed='11.176', speedFactor='1.0', speedDev='0.0')
        ET.SubElement(routes, 'route', id='corridor', edges=' '.join(route_edges))
        for identifier, depart in scheduled.items():
            ET.SubElement(routes, 'vehicle', id=identifier, type='passenger', route='corridor', depart=str(depart), departLane='best', departSpeed='max')
        routes_path = run_dir/'demand.rou.xml'
        ET.ElementTree(routes).write(routes_path, encoding='utf-8', xml_declaration=True)
        duration = inputs['duration_sec']
        all_metrics = {'baseline': [], 'early': [], 'late': []}
        playback = {t: {'time_sec': t, 'baseline': [], 'early': [], 'late': []} for t in range(0, duration+1, 10)}
        deadline = time.monotonic() + min(getattr(self.settings, 'job_timeout_seconds', 180), 180)
        alternatives = [('baseline', None), ('early', inputs['early_clearance_sec']), ('late', inputs['late_clearance_sec'])]
        total_steps = len(inputs['seeds'])*3*duration
        finished_steps = 0
        for seed_index, seed in enumerate(inputs['seeds']):
            for name, clearance in alternatives:
                metrics, frames = self._run_alternative(traci, binary, run_dir, routes_path, manifest, scheduled, inputs, name, clearance, seed, cancel_event, deadline,
                                                       lambda step: progress(min(.99, (finished_steps+step)/total_steps)), seed_index == 0)
                all_metrics[name].append({'seed': seed, **metrics})
                if seed_index == 0:
                    for t, vehicles in frames.items():
                        playback[t][name] = vehicles
                finished_steps += duration
        aggregates = {}
        for name, runs in all_metrics.items():
            aggregate = _aggregate_metrics(runs)
            aggregate['affected_road_ids'] = [manifest['blockage_road_id']] if name != 'baseline' else []
            aggregates[name] = aggregate
        early, late = aggregates['early'], aggregates['late']
        comparison = {'delay_saved_sec': round(late['total_delay_sec']-early['total_delay_sec'], 2),
                      'additional_completed_vehicles': round(early['throughput']-late['throughput'], 2),
                      'queue_reduction_vehicles': round(late['peak_queue_vehicles']-early['peak_queue_vehicles'], 2),
                      'elapsed_journey_time_saved_sec': round(late['total_elapsed_journey_time_sec']-early['total_elapsed_journey_time_sec'], 2),
                      'comparison': 'late minus early delay/queue; early minus late throughput; same demand and paired seeds',
                      'seed_count': len(inputs['seeds'])}
        result = {'id': run_id, 'state': 'succeeded', 'scenario': inputs, 'engine': version, 'network_version': manifest['network_version'], 'network_sha256': manifest['network_sha256'],
                  'data_origin': 'synthetic', 'execution_mode': 'real_provider', **aggregates, 'comparison': comparison,
                  'assumptions': manifest['assumptions'] + ['Uniform synthetic vehicle arrivals; no calibration to current traffic sensors.', 'Severe obstruction caps every lane of the selected link at 0.1 m/s until clearance; no rerouting.', 'Playback shows only the first seed. Metrics are arithmetic means across paired seeds except completed travel time, which is weighted by completed vehicle count.', 'This Manhattan scenario is separate from workshop archive footage and cannot establish effects of an archived incident.'],
                  'playback_url': f'api/simulations/{run_id}/playback', 'created_at': utcnow(),
                  'playback': {'network_id': inputs['network_id'], 'frame_interval_sec': 10, 'frames': list(playback.values()), 'data_origin': 'synthetic'}}
        (run_dir/'result.json').write_text(json.dumps(result, indent=2))
        progress(1.0)
        return result

    def _run_alternative(self, traci, binary, run_dir, routes_path, manifest, scheduled, inputs, name, clearance, seed, cancel_event, deadline, progress, record):
        if cancel_event.is_set():
            raise ProviderError('simulation_cancelled', 'Simulation was cancelled.', 409)
        path = run_dir/f'{name}-{seed}'
        path.mkdir()
        try:
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1', 0))
                port = reservation.getsockname()[1]
        except OSError:
            raise ProviderError('sumo_socket_unavailable', 'The SUMO worker needs permission to bind a private local TraCI socket.') from None
        trip_path = path/'tripinfo.xml'
        command = [binary, '--net-file', str(NETWORK_DIR/'nyc-demo-corridor.net.xml.gz'), '--route-files', str(routes_path), '--seed', str(seed), '--step-length', '1', '--end', str(inputs['duration_sec']), '--remote-port', str(port), '--no-step-log', 'true', '--duration-log.disable', 'true', '--time-to-teleport', '-1', '--tripinfo-output', str(trip_path), '--tripinfo-output.write-unfinished', 'true', '--no-warnings', 'true']
        proc, connection = None, None
        done = threading.Event()
        frames = {0: []}
        peak_queue, queue_sum = 0, 0
        try:
            with (path/'sumo.log').open('w') as log:
                proc = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
                def watchdog():
                    while not done.wait(.1):
                        if cancel_event.is_set() or time.monotonic() >= deadline:
                            if proc.poll() is None:
                                try:
                                    os.killpg(proc.pid, signal.SIGTERM)
                                except ProcessLookupError:
                                    pass
                            return
                monitor = threading.Thread(target=watchdog, daemon=True)
                monitor.start()
                connection = traci.connect(port=port, host='127.0.0.1', proc=proc, numRetries=30, waitBetweenRetries=.05)
                lane_ids = [manifest['blockage_edge']+'_'+str(i) for i in range(connection.edge.getLaneNumber(manifest['blockage_edge']))]
                original_speeds = {lane: connection.lane.getMaxSpeed(lane) for lane in lane_ids}
                for t in range(inputs['duration_sec']):
                    if cancel_event.is_set():
                        raise ProviderError('simulation_cancelled', 'Simulation was cancelled.', 409)
                    if time.monotonic() >= deadline:
                        raise ProviderError('simulation_timeout', 'Simulation exceeded the bounded runtime.')
                    if clearance is not None and t == inputs['blockage_start_sec']:
                        for lane in lane_ids:
                            connection.lane.setMaxSpeed(lane, .1)
                    if clearance is not None and t == clearance:
                        for lane, speed in original_speeds.items():
                            connection.lane.setMaxSpeed(lane, speed)
                    connection.simulationStep()
                    active = connection.vehicle.getIDList()
                    pending = connection.simulation.getPendingVehicles()
                    queue = sum(connection.vehicle.getSpeed(v) <= .1 for v in active) + len(pending)
                    peak_queue = max(peak_queue, queue)
                    queue_sum += queue
                    if (t+1) % 10 == 0:
                        progress(t+1)
                        if record:
                            frame = []
                            for vehicle in active:
                                lon, lat = connection.simulation.convertGeo(*connection.vehicle.getPosition(vehicle))
                                frame.append({'id': vehicle, 'lon': round(lon, 7), 'lat': round(lat, 7), 'speed_kph': round(connection.vehicle.getSpeed(vehicle)*3.6, 2), 'road_id': 'osm-'+connection.vehicle.getRoadID(vehicle)})
                            frames[t+1] = frame
                connection.close()
                connection = None
                proc.wait(timeout=5)
                if proc.returncode:
                    raise ProviderError('sumo_failed', 'SUMO exited before writing complete scenario results.')
            return _metrics(trip_path, scheduled, inputs['duration_sec'], peak_queue, queue_sum), frames
        except ProviderError:
            raise
        except Exception:
            if cancel_event.is_set():
                raise ProviderError('simulation_cancelled', 'Simulation was cancelled.', 409) from None
            if time.monotonic() >= deadline:
                raise ProviderError('simulation_timeout', 'Simulation exceeded the bounded runtime.') from None
            raise ProviderError('sumo_failed', 'SUMO/TraCI could not complete this scenario; inspect the local run log.') from None
        finally:
            done.set()
            if connection is not None:
                try:
                    connection.close(wait=False)
                except Exception:
                    pass
            if proc is not None and proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=3)
