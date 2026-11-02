"""Fresh, qualified collection with durable whole-episode audit before replay.

This reuses the physical session, never imports/promotes candidate archives.
No optimizer exists here. A collector owns one session/replay/output directory.
Failed publication can be retried without rerunning physical interaction.
"""
from copy import deepcopy
import gzip
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import time

import numpy as np

from .admission import validate_case, validate_config
from .b2_admission import CollectionAdmission
from .episode_buffer import EpisodeBuffer, _safe_error_archive
from .audited_replay import AuditedReplay
from .outcome import classify_outcome


class FormalEpisodeBuffer(EpisodeBuffer):
    def finalize(self, *, valid_for_learning, sink):
        if type(valid_for_learning) is not bool:
            raise TypeError('Learning permission must be a boolean')
        if valid_for_learning and self._finite and (not self._pending or not self._boundary):
            raise ValueError('Nonempty completed episode required for publication')
        return super().finalize(valid_for_learning=valid_for_learning, sink=sink)


class EngineeringSampler:
    """One deterministic initialization stream; each call is one retained attempt."""
    def __init__(self, config):
        validate_config(config)
        self.rng = np.random.Generator(np.random.PCG64(config['sampling']['seed']))
        self.count = 0

    def next_case(self):
        xy = self.rng.uniform(-50e-6, 50e-6, size=2)
        case = dict(name=f'engineering_{self.count:06d}', x_offset_m=float(xy[0]),
            y_offset_m=float(xy[1]), roll_rad=0., pitch_rad=0.,
            start_origin_z_m=-.004, target_depth_m=.004)
        self.count += 1
        return case


def _replace_json(temporary, path):
    # A Windows reader without delete sharing can briefly deny replacement.
    # Retry only this already-flushed file, never a learning update or rollout.
    delays = (0., .01, .02, .04, .08, .16, .25, .25, .25)
    for attempt, delay in enumerate(delays, 1):
        if delay:
            time.sleep(delay)
        try:
            os.replace(temporary, path)
        except PermissionError as exc:
            if os.name != 'nt' or getattr(exc, 'winerror', None) not in (5, 32, 33):
                raise
            if attempt == len(delays):
                exc.add_note(f'Atomic JSON replacement still denied after {attempt} attempts '
                             f'and {sum(delays):.2f}s scheduled waits; staged data retained at {temporary}; '
                             'no optimizer or physical action was retried.')
                raise
        else:
            if attempt > 1:
                logging.getLogger(__name__).warning(
                    'atomic_json_replace_recovered: path=%s attempts=%d; no learning action repeated',
                    path, attempt)
            return


def _write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    content = json.dumps(_safe_error_archive(value), ensure_ascii=False, indent=2, allow_nan=False)
    with temporary.open('w', encoding='utf-8') as stream:
        stream.write(content); stream.flush(); os.fsync(stream.fileno())
    _replace_json(temporary, path)


def _write_archive(path, value):
    path = Path(path)
    content = json.dumps(_safe_error_archive(value), ensure_ascii=False, allow_nan=False).encode('utf-8')
    data = gzip.compress(content, mtime=0)
    if path.exists():
        if path.read_bytes() != data: raise ValueError('Existing immutable archive differs')
    else:
        temporary = path.with_suffix('.tmp')
        with temporary.open('wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    return hashlib.sha256(data).hexdigest()


def _new_session(config):
    from .guarded_environment import GuardCandidateConfig, LearningEnvironment
    from .residual_session import ResidualSession
    return ResidualSession(environment=LearningEnvironment(
        guard_config=GuardCandidateConfig(**config['guard'])), action_scale=config['action']['scale'])


def _physical_audit(session):
    from tools.validation.native313_matrix_audit import actual_stop_pass
    from tools.validation.run_contact_candidate_stop import physical_tail_pass
    e = session.env
    facts = e.guard_facts
    stopped = bool(session.done and e.phase == 'STOPPING' and
        actual_stop_pass(e.stop_samples, e.events, session.stop_time, e.data.time, e.config.timestep) and
        physical_tail_pass(e.stop_samples, e.data.time, e.config.timestep))
    return classify_outcome(simulation_valid=facts['simulation_valid'],
        contact_guard=bool(facts['contact_reasons']), motion_violation=bool(facts['motion_reasons']),
        full_success=session.task_finished and session.reason == 'GEOMETRIC_SUCCESS',
        physical_stopped=stopped)


def _vector(snapshot):
    value = np.asarray(snapshot.policy_observation, dtype=np.float32)
    if value.shape != (120,) or not np.isfinite(value).all() or (abs(value) > 10).any():
        raise ValueError('Invalid policy observation')
    return value.copy()


class AdmittedCollector:
    admission_type = CollectionAdmission
    case_validator = staticmethod(validate_case)

    def __init__(self, *, admission, replay, output):
        required = CollectionAdmission if type(self).admission_type is AdmittedCollector.admission_type else self.admission_type
        if not isinstance(admission, required) or type(replay) is not AuditedReplay:
            raise TypeError('Bound CollectionAdmission and AuditedReplay required')
        self.admission, self.replay = admission, replay
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.attempts = []  # Summaries only; raw data is on disk after publication.
        self.session = None
        self.active = self._blocked = False
        self._pending = None
        self._status_pending = False

    def start(self, episode_id, *, case, seed):
        if self.active or self._pending is not None or self._blocked:
            raise RuntimeError('Active/pending/rejected attempt prevents reset')
        if not isinstance(episode_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', episode_id):
            raise ValueError('Safe, nonempty episode ID required')
        self._folder = self.output / episode_id
        self._folder.mkdir(exist_ok=False)
        self._blocked = True
        self._record = dict(episode_id=episode_id, case=_safe_error_archive(case), seed=seed,
            qualification_sha256=self.admission.expected_digest, status='initializing',
            steps=0, committed=0, discarded=0)
        self.attempts.append(self._record)
        self.buffer = FormalEpisodeBuffer()
        self._fault_info = None
        self.session = None
        _write_json(self._folder / 'status.json', self._record)
        try:
            if type(seed) is not int or seed < 0: raise ValueError('Explicit nonnegative integer seed required')
            if not isinstance(case, dict): raise TypeError('Explicit case dictionary required')
            self.admission.verify(case)
            self.case_validator(case)
            from tools.validation.run_contact_cases import ContactCase
            selected = ContactCase(**case)
            self.session = _new_session(self.admission.config)
            self._obs = _vector(self.session.reset(selected, seed=seed))
        except Exception as exc:
            self._record.update(status='rejected_before_reset', error=repr(exc))
            self._blocked = True
            _write_json(self._folder / 'status.json', self._record)
            raise
        self.active = True
        self._record['status'] = 'collecting'
        _write_json(self._folder / 'status.json', self._record)
        self._blocked = False

    def collect(self, policy, steps, *, cut_at_end=False, deterministic=False):
        if type(steps) is not int or steps <= 0 or type(cut_at_end) is not bool:
            raise ValueError('Positive steps and boolean cut_at_end required')
        if not self.active: raise RuntimeError('No active qualified episode')
        count = 0
        for i in range(steps):
            try:
                if self._record['steps'] >= self.admission.config['sampling']['watchdog_cycles']:
                    raise RuntimeError('Diagnostic cycle watchdog exceeded')
                action, _ = policy.predict(self._obs.copy(), deterministic=deterministic)
                before = self.session.prepare_cycle()
                result = self.session.advance_cycle(action)
                self._obs = _vector(result.next_snapshot)
                terminated = bool(result.done)
                truncated = bool(cut_at_end and i == steps - 1 and not terminated)
                self.buffer.stage(dict(observation=_vector(before).tolist(), next_observation=self._obs.tolist(),
                    action=result.action_log['experience_action'], reward=result.reward_terms['total'],
                    terminated=terminated, truncated=truncated, action_active=before.residual_enabled,
                    next_action_active=result.next_snapshot.residual_enabled, dt=result.dt,
                    discount=math.exp(-result.dt / 10), reward_terms=deepcopy(result.reward_terms),
                    action_log=deepcopy(result.action_log), trace_row=deepcopy(result.trace_row),
                    events=deepcopy(result.events)))
                count += 1; self._record['steps'] += 1
                if truncated: self._stop_tail()
            except Exception as exc:
                self._abort(exc)
                raise
            if terminated or truncated:
                self._seal()
                break
        return dict(steps=count, total_steps=self._record['steps'], episode_finished=not self.active)

    def _stop_tail(self):
        self.session.start_external_tail()
        for _ in range(1500):
            if self.session.done: return
            self.session.advance_cycle([0.] * 4)
        if not self.session.done: raise RuntimeError('Safety tail did not complete')

    def _abort(self, exc):
        self._blocked = True
        self._fault_info = {'error': repr(exc)}
        try:
            if not self.session.done: self._stop_tail()
        except Exception as stop_exc:
            self._fault_info['stop_error'] = repr(stop_exc)
        try: self._seal()
        except Exception as archive_exc:
            self._record['publication_error'] = repr(archive_exc)

    def _seal(self):
        self.active = False
        self._blocked = True
        self._record['status'] = 'pending_publication'
        audit_error = None
        try:
            outcome = _physical_audit(self.session)
        except Exception as exc:
            audit_error = exc
            self._fault_info = dict(self._fault_info or {}, audit_error=repr(exc))
            outcome = classify_outcome(simulation_valid=False, contact_guard=False,
                motion_violation=False, full_success=False, physical_stopped=False)
        if self._fault_info is not None: outcome['valid_for_learning'] = False
        rows = []
        result = self.buffer.finalize(valid_for_learning=outcome['valid_for_learning'], sink=rows)
        if result['discarded']:
            rows = self.buffer.quarantined
            if outcome['valid_for_learning']:
                outcome.update(valid_for_learning=False, data_valid=False)
                self._fault_info = {'error': 'Nonfinite or unarchivable episode data'}
        if not outcome['valid_for_learning']: self._blocked = True
        e = self.session.env
        self._pending = dict(episode_id=self._record['episode_id'], case=self._record['case'],
            seed=self._record['seed'], qualification_sha256=self.admission.expected_digest,
            outcome=outcome, fault=self._fault_info, transitions=rows,
            guard_facts=e.guard_facts, events=deepcopy(e.events), stop_samples=deepcopy(e.stop_samples),
            stop_time=self.session.stop_time, audit_end_time_s=float(e.data.time),
            final_session=dict(task_finished=getattr(self.session, 'task_finished', False),
                reason=self.session.reason, phase=getattr(e, 'phase', None)),
            optimizer_steps=0)
        # The complete pending record now exists before any fallible disk write.
        _write_json(self._folder / 'status.json', self._record)
        self.retry_publication()
        if audit_error is not None: raise audit_error

    def retry_publication(self):
        if self._status_pending:
            _write_json(self._folder / 'status.json', self._record)
            self._status_pending = False
            self._blocked = not self._record['valid_for_learning']
            return
        if self._pending is None: raise RuntimeError('No pending audited publication')
        raw = self._pending
        # Preserve the attempt even if current sources or the runtime went stale.
        sha = _write_archive(self._folder / 'episode.json.gz', raw)
        self.admission.verify(raw['case'])
        result = self.replay.publish(raw['episode_id'], raw['transitions'],
            outcome=raw['outcome'], training_admitted=True)
        self._record.update(result, physical_stopped=raw['outcome']['physical_stopped'],
            task_outcome=raw['outcome']['task_outcome'], simulation_valid=raw['outcome']['simulation_valid'],
            valid_for_learning=raw['outcome']['valid_for_learning'], archive_sha256=sha,
            audit_end_time_s=raw['audit_end_time_s'],
            status='published' if raw['outcome']['valid_for_learning'] else 'rejected')
        # The replay transaction has committed. A following status-write failure
        # must never cause a duplicate publication on retry.
        self._pending = None
        self._status_pending = True
        self.session = None
        self.buffer = None
        self.retry_publication()
