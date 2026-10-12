"""XY50 archive audit plus same-cycle permission checks for this paired stage.

Execution identity/authorization is bound by the calling contract and runtime.
This rule checks the stage mode and every current/next policy permission; it
does not require SEARCH to occur or grant a training budget.
"""
import importlib.util
from pathlib import Path

import numpy as np


_source = Path(__file__).resolve().parent.parent / 'b2_frozen_c2000_closeout_20261001/deployment_rules.py'
_spec = importlib.util.spec_from_file_location('_stage_sealed_deployment_rules', _source)
_sealed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sealed)


class StageRules(_sealed.DeploymentRules):
    def __init__(self, mode):
        if type(mode) is not str or mode not in ('F', 'S'):
            raise ValueError('Registered stage mode F or S required')
        super().__init__([.00005, .00005, .0005, .0005])
        self.mode = mode
        self.version = 'stage_permission_mapping_v1_' + mode

    def _permission(self, observation):
        obs = np.asarray(observation)
        if (obs.shape != (120,) or obs.dtype.kind not in 'iuf' or
                not np.isfinite(obs).all() or np.any(np.abs(obs) > 10)):
            raise ValueError('Finite versioned policy observation required')
        for begin, end in ((53, 58), (58, 62), (62, 66), (66, 75)):
            values = obs[begin:end]
            if not np.isin(values, (0., 1.)).all() or values.sum() != 1:
                raise ValueError('Policy phase, physical phase and decisions must be one-hot')
        if not np.isin(obs[75:86], (0., 1.)).all():
            raise ValueError('Policy permission and guard facts must be boolean')
        if obs[75] != float(obs[66] == 0):
            raise ValueError('Pending permission flag differs from the observed decision')
        allowed = obs[55] == 1 or (self.mode == 'F' and obs[53] == 1)
        expected = bool(allowed and obs[58] == 1 and obs[75] == 0 and
            obs[77] == 1 and not obs[78:86].any())
        if obs[76] != float(expected):
            raise ValueError('Policy action_active differs from registered stage permission')
        return expected

    def classify(self, raw):
        if not isinstance(raw, dict) or raw.get('stage_mode') != self.mode:
            raise ValueError('Archive belongs to a different stage mode')
        for row in raw['transitions']:
            active = self._permission(row['observation'])
            next_active = self._permission(row['next_observation'])
            if (type(row['action_active']) is not bool or row['action_active'] is not active or
                    type(row['next_action_active']) is not bool or row['next_action_active'] is not next_active):
                raise ValueError('Transition flags differ from same-cycle policy permission')
            log = row['action_log']
            expected = log['raw_action'] if active else [0.] * 4
            if log.get('experience_action') != expected or row['action'] != expected:
                raise ValueError('Experience action differs from registered permission')
        result = super().classify(raw)
        return dict(result, stage_mode=self.mode)

    def receipt_valid(self, receipt):
        force = receipt.get('task_outcome') == 'CONTACT_GUARD'
        expected = dict(version=self.version, kind='force_failure' if force else 'guard_clear', stage_mode=self.mode)
        return (receipt.get('stage_mode') == self.mode and receipt.get('guard_clear') is (not force)
            and receipt.get('task_outcome') in ('FULL_SUCCESS', 'TASK_FAILURE', 'CONTACT_GUARD')
            and receipt.get('learning_eligibility') == expected)
