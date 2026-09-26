"""Untrained-policy collector for the existing candidate ResidualEnv protocol.

Batch limits pause, not reset/truncate. Explicit cuts delegate the actual stop
audit to the env. Candidate attempts are ALWAYS denied replay admission: there
is intentionally no flag to override that here. No learn/update or auto-resample.
The replay's positive path is separately qualified on synthetic audited data.
Single owner of env/policy/replay; attempts are an in-memory diagnostic ledger,
not a durable trainer checkpoint. Generic SB3/TimeLimit/vector wrappers cannot
substitute for ResidualEnv's audited attempts protocol.
"""
from copy import deepcopy

from .episode_buffer import _safe_error_archive


class CandidateCollector:
    def __init__(self, *, env, policy, replay):
        self.env, self.policy, self.replay = env, policy, replay
        self.attempts = []
        self.active = False
        self._blocked = False
        self._pending = None
        self._seen = set()

    def start(self, episode_id, *, seed=None, options=None):
        if self.active or self._pending is not None or self._blocked:
            raise RuntimeError('Finish/retry current attempt; uncertain stop forbids reset')
        if not isinstance(episode_id, str) or not episode_id:
            raise ValueError('Nonempty episode_id required')
        if episode_id in self._seen:
            raise RuntimeError('Attempt ID already used')
        self._seen.add(episode_id)
        self._record = dict(episode_id=episode_id, seed=_safe_error_archive(seed),
                            options=_safe_error_archive(options), status='initializing', steps=0,
                            emergency_cut_attempts=0, emergency_cut_returned_steps=0)
        self.attempts.append(self._record)
        self._env_start = len(self.env.attempts)
        try:
            self._obs, info = self.env.reset(seed=seed, options=options)
            self.active = True
            if info.get('training_admitted') is not False:
                raise ValueError('Only explicitly non-admitted candidate environments supported')
        except Exception as exc:
            self._record['fault'] = dict(error=repr(exc))
            if self.active:
                self._abort(exc)
            else:
                self._record['status'] = 'failed'
                if len(self.env.attempts) > self._env_start:
                    self._record['environment'] = deepcopy(self.env.attempts[-1])
            raise
        self._record['status'] = 'collecting'

    def collect(self, steps, *, cut_at_end=False, deterministic=False):
        if type(steps) is not int or steps <= 0 or type(cut_at_end) is not bool:
            raise ValueError('Positive steps and boolean cut_at_end required')
        if not self.active:
            raise RuntimeError('Start an explicit attempt before collecting')
        collected = 0
        for i in range(steps):
            try:
                action, _ = self.policy.predict(self._obs.copy(), deterministic=deterministic)
                call = self.env.truncate_after_step if cut_at_end and i == steps - 1 else self.env.step
                self._obs, _, terminated, truncated, info = call(action)
                collected += 1
                self._record['steps'] += 1
                if info.get('training_admitted') is not False:
                    raise ValueError('Candidate unexpectedly reports training admission')
            except Exception as exc:
                self._abort(exc)
                raise
            if terminated or truncated:
                self._seal()
                break
        return dict(steps=collected, total_steps=self._record['steps'], episode_finished=not self.active)

    def _abort(self, exc):
        self._record['fault'] = dict(error=repr(exc))
        # A step may already have failed closed and archived the episode. Only
        # initiate a real zero-action cutoff when no final audit exists yet.
        if len(self.env.attempts) == self._env_start:
            self._record['emergency_cut_attempts'] += 1
            try:
                self.env.truncate_after_step([0.] * 4)
                self._record['emergency_cut_returned_steps'] += 1
            except Exception as stop_exc:
                self._record['fault']['stop_error'] = repr(stop_exc)
        try:
            self._seal()
        except Exception as publication_exc:
            self._record['fault']['publication_error'] = repr(publication_exc)
            # Keep the original fault as the raised exception. Retry publication
            # explicitly; never rerun the policy or physical stop to repair it.

    def _seal(self):
        # Latch before copying or allocating diagnostics. If these fail, a new
        # reset must not discard this audit or assume that physical stop passed.
        self._blocked = True
        self.active = False
        self._record['status'] = 'pending_publication'
        self._pending = self._record
        if len(self.env.attempts) != self._env_start + 1:
            self._record['status'] = 'failed'
            self._pending = None
            raise RuntimeError('Missing or ambiguous complete environment audit; reset blocked')
        self._record['audit_index'] = self._env_start
        self.retry_publication()

    def retry_publication(self):
        if self._pending is None:
            raise RuntimeError('No pending publication')
        record = self._pending
        try:
            if 'environment' not in record:
                # The collector owns the env: while pending, no new interaction
                # occurs and this exact audit remains available for copy retry.
                record['environment'] = deepcopy(self.env.attempts[record['audit_index']])
            environment = record['environment']
            self._blocked = environment['outcome'].get('physical_stopped') is not True
            record['archived_row_count'] = len(environment['quarantined'])
            publication = self.replay.publish(record['episode_id'], environment['quarantined'],
                outcome=environment['outcome'], training_admitted=False)
        except Exception as exc:
            record.setdefault('publication_errors', []).append(repr(exc))
            raise
        record['publication'] = publication
        record['status'] = 'failed' if 'fault' in record else 'quarantined'
        self._pending = None
