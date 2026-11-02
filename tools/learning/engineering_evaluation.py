"""Fixed paired development evaluation, isolated from training replay and RNG."""
import json
import math
import numpy as np

from .admission import digest
from .admitted_collection import AdmittedCollector, _write_archive, _write_json
from .audited_replay import AuditedReplay
from .b2_training_admission import SPLIT, SPLIT_SHA256, execution_contract
from .runtime import ROOT


def evaluation_cases():
    path = ROOT / SPLIT
    if digest(path) != SPLIT_SHA256: raise ValueError('Frozen split changed')
    split = json.loads(path.read_text(encoding='utf-8'))
    indexed = {r['id']: r for r in split['splits']['validation']['cases']}
    cases = []
    for key in execution_contract()['evaluation_ids']:
        r = indexed[key]
        if r['group'] != 'small_xy' or any(r[k] != 0 for k in ('roll_deg', 'pitch_deg', 'yaw_deg')):
            raise ValueError('Development case is outside frozen engineering scope')
        cases.append(dict(name=key, x_offset_m=r['x_um'] / 1e6, y_offset_m=r['y_um'] / 1e6,
            roll_rad=0., pitch_rad=0., start_origin_z_m=r['start_origin_z_m'], target_depth_m=.004))
    return cases


class ZeroPolicy:
    def predict(self, observation, deterministic=True): return np.zeros(4, dtype=np.float32), None


class FrozenPolicy:
    def __init__(self, updater): self.updater = updater
    def predict(self, observation, deterministic=True): return self.updater.predict(observation, deterministic=True)


class EvaluationCollector(AdmittedCollector):
    def __init__(self, *, admission, output, checkpoint_sha256, method, updater):
        if method not in execution_contract()['evaluation_methods']: raise ValueError('Unknown evaluation method')
        self.method, self.checkpoint_sha256, self.updater = method, checkpoint_sha256, updater
        super().__init__(admission=admission, replay=AuditedReplay(capacity=100000), output=output)

    def start(self, episode_id, *, case, seed):
        self._start_count = dict(self.updater.counts)
        self._policy_sha = self.updater.fingerprints()['actor']
        super().start(episode_id, case=case, seed=seed)

    def collect(self, policy, steps, *, cut_at_end=False, deterministic=True):
        if cut_at_end or deterministic is not True: raise ValueError('Only complete deterministic evaluation is permitted')
        if self.method == 'zero_b2' and type(policy) is not ZeroPolicy: raise ValueError('Zero baseline policy required')
        if self.method == 'sac' and (type(policy) is not FrozenPolicy or policy.updater is not self.updater):
            raise ValueError('Frozen selected SAC policy required')
        return super().collect(policy, steps, deterministic=True)

    def retry_publication(self):
        if self._status_pending:
            _write_json(self._folder / 'status.json', self._record)
            self._status_pending = False
            self._blocked = not self._record['valid_for_learning']
            return
        if self._pending is None: raise RuntimeError('No pending evaluation archive')
        raw = self._pending
        raw.update(training_admitted=False, evaluation_method=self.method,
            checkpoint_sha256=self.checkpoint_sha256, policy_sha256=self._policy_sha,
            optimizer_steps_start=self._start_count['critic'], optimizer_steps=self.updater.counts['critic'])
        sha = _write_archive(self._folder / 'episode.json.gz', raw)
        if self.updater.counts != self._start_count or self.updater.fingerprints()['actor'] != self._policy_sha:
            raise RuntimeError('Evaluation changed the selected policy')
        self.admission.verify(raw['case'])
        result = self.replay.publish(raw['episode_id'], raw['transitions'], outcome=raw['outcome'], training_admitted=False)
        self._record.update(result, training_admitted=False, evaluation_method=self.method,
            checkpoint_sha256=self.checkpoint_sha256, policy_sha256=self._policy_sha,
            physical_stopped=raw['outcome']['physical_stopped'], task_outcome=raw['outcome']['task_outcome'],
            simulation_valid=raw['outcome']['simulation_valid'], valid_for_learning=raw['outcome']['valid_for_learning'],
            archive_sha256=sha, status='evaluation_archived' if raw['outcome']['valid_for_learning'] else 'rejected')
        self._pending = None; self._status_pending = True; self.session = None; self.buffer = None
        self.retry_publication()


def episode_metrics(raw):
    rows = raw['transitions']; outcome = raw['outcome']
    forces = []; torques = []; effective = []; commands = []; clips = []
    for row in rows:
        dt = row['dt']; terms = row['reward_terms']; log = row['action_log']
        forces.append(.025 * math.sqrt(max(0., -terms['force'] / (.2 * dt))))
        torques.append(.0005 * math.sqrt(max(0., -terms['torque'] / (.2 * dt))))
        effective.append(np.asarray(log['effective_command_delta'], dtype=float))
        commands.append(np.asarray(log['actual_end_limited_command'], dtype=float))
        clips.append(bool(np.any(np.abs(effective[-1] - log['applied_residual']) > 1e-15)))
    effective = np.asarray(effective).reshape(-1, 6); commands = np.asarray(commands).reshape(-1, 6)
    delta = np.diff(commands, axis=0)
    norm_mean = lambda a: float(np.linalg.norm(a, axis=1).mean()) if len(a) else 0.
    return dict(success=outcome['task_outcome'] == 'FULL_SUCCESS', task_outcome=outcome['task_outcome'],
        simulation_valid=outcome['simulation_valid'], physical_stopped=outcome['physical_stopped'],
        cycles=len(rows), simulated_duration_s=sum(r['dt'] for r in rows),
        task_stop_time_s=raw['stop_time'], audit_end_time_s=raw['audit_end_time_s'],
        **{'return': sum(r['reward'] for r in rows)}, force_peak_N=max(forces, default=0.), torque_peak_Nm=max(torques, default=0.),
        sampled_penetration_peak_m=max((r['trace_row']['penetration_m'] for r in rows), default=0.),
        contact_cycles=sum(r['trace_row']['contact_count'] > 0 for r in rows),
        active_cycles=sum(bool(r['action_active']) for r in rows),
        effective_action_cycles=int(np.any(np.abs(effective) > 1e-15, axis=1).sum()), clipped_cycles=sum(clips),
        max_continuously_clipped_s=max((r['action_log']['continuously_clipped_s'] for r in rows), default=0.),
        mean_effective_translation_m_s=norm_mean(effective[:, :3]), mean_effective_rotation_rad_s=norm_mean(effective[:, 3:]),
        mean_command_step_translation_m_s=norm_mean(delta[:, :3]), mean_command_step_rotation_rad_s=norm_mean(delta[:, 3:]),
        final_xy_error_m=float(np.linalg.norm(rows[-1]['trace_row']['position_m'][:2])) if rows else None)
