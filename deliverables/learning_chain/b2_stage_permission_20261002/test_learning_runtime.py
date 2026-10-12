"""Offline component tests: synthetic archives, real replay/networks/disk, no compute."""
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
os.environ['MPLCONFIGDIR'] = str(ROOT/'tmp/learning_mpl_cache')
import numpy as np
import torch
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import mujoco
from tools.learning.actor_lr_contract import execution_config
from tools.learning.sac_checkpoint import _same


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def configuration(arm):
    result = execution_config('A')
    result['version'] = 'stage_permission_test_v1'
    result['action'].update(scale=[.00005, .00005, .0005, .0005],
                            enabled_stages=['INSERT', 'SEARCH'] if arm == 'F' else ['SEARCH'])
    result['comparison'] = dict(arm=arm)
    return result


class SyntheticRules:
    """Physics eligibility is tested by Task 1; these are labelled synthetic data."""
    version = 'synthetic_stage_rules_v1'

    def __init__(self, mode):
        self.mode = mode

    def classify(self, raw):
        if raw.get('stage_mode') != self.mode or raw.get('synthetic') is not True:
            raise ValueError('Synthetic mode mismatch')
        return dict(version=self.version, kind='guard_clear')

    def accepts(self, raw):
        self.classify(raw)
        return True


class Ledger:
    def __init__(self):
        self.state = dict(binding_sha256='a'*64, authorization_sha256='b'*64,
                          datasets={}, updates={a: dict(attempted=0, completed=0) for a in ('F', 'S')})
        self.results = []
        self.lease = None

    def rows(self, stage, arm=None):
        return [r for r in self.results if r['stage'] == stage and (arm is None or r['arm'] == arm)]

    def register_dataset(self, arm, pin, ids):
        self.state['datasets'][arm] = dict(manifest_sha256=pin, ids=ids)

    def healthy(self):
        if self.lease is not None:
            raise RuntimeError('Active update')

    def reserve_update(self, arm):
        self.healthy()
        self.state['updates'][arm]['attempted'] += 1
        self.lease = dict(arm=arm, batch=self.state['updates'][arm]['attempted'])
        return self.lease

    def finish_update(self, token):
        if token != self.lease:
            raise RuntimeError('Wrong token')
        self.state['updates'][token['arm']]['completed'] += 1
        self.lease = None


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HERE/'learning_runtime.py').exists(), 'New stage learning runtime is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.C = types.ModuleType('paired_contract')
        self.C.ROOT = self.root
        self.C.HERE = self.root
        self.C.canonical = canonical
        self.C.digest = digest
        self.C.read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
        self.C.write = lambda p, value: Path(p).write_text(json.dumps(value, allow_nan=False), encoding='utf-8')
        self.C.config = configuration
        self.C.scope = lambda: dict(seed=2026092716)
        rule_module = types.ModuleType('stage_rules')
        rule_module.StageRules = SyntheticRules
        with patch.dict(sys.modules, paired_contract=self.C, stage_rules=rule_module):
            spec = importlib.util.spec_from_file_location('tested_stage_learning_runtime', HERE/'learning_runtime.py')
            self.R = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.R)
        self.ledger = Ledger()
        self.calls = dict(model=0, optimizer=0, physics=0)

        def forbid(kind):
            def stop(*args, **kwargs):
                self.calls[kind] += 1
                raise AssertionError('Offline tests forbid '+kind)
            return stop
        self.addCleanup(patch.stopall)
        patch.object(torch.nn.Module, '_call_impl', forbid('model')).start()
        patch.object(torch.optim.Adam, 'step', forbid('optimizer')).start()
        for name in ('mj_step', 'mj_step1', 'mj_step2', 'mj_forward', 'mj_resetData', 'mj_resetDataKeyframe'):
            patch.object(mujoco, name, forbid('physics')).start()

    def tearDown(self):
        if hasattr(self, 'calls'):
            self.assertEqual(self.calls, dict(model=0, optimizer=0, physics=0))

    def archive(self, arm='F', index=0, role='warmup', count=0):
        names = ('x_pos_100', 'x_neg_100', 'y_pos_100', 'y_neg_100')
        xy = ((.0001, 0.), (-.0001, 0.), (0., .0001), (0., -.0001))[index]
        case = dict(name=names[index], x_offset_m=xy[0], y_offset_m=xy[1], roll_rad=0., pitch_rad=0.,
                    start_origin_z_m=-.004, target_depth_m=.004)
        key = f'{role}_{arm}_{names[index]}'
        identity = dict(id=key, stage=role, arm=arm, case_index=index, case=case)
        obs = [0.]*120
        row = dict(observation=obs, next_observation=obs, action=[.1]*4, reward=1., dt=.002,
                   discount=math.exp(-.002/10), action_active=True, next_action_active=False,
                   terminated=True, truncated=False)
        raw = dict(episode_id=key, current_identity=identity, case=case, seed=2026092716,
                   qualification_sha256='a'*64, stage_mode=arm, training_admitted=True,
                   optimizer_steps_start=count, optimizer_steps=count, synthetic=True, fault=None,
                   outcome=dict(simulation_valid=True, physical_stopped=True, valid_for_learning=True),
                   guard_facts=dict(contact_reasons=[], motion_reasons=[], invalid_reasons=[]), transitions=[row])
        path = self.root/(key+'.json.gz')
        self.write_raw(path, raw)
        result = dict(**identity, completed=True, guard_hit=False, simulation_valid=True, physical_stopped=True,
                      archive_path=path.name, archive_sha256=digest(path))
        self.ledger.results.append(result)
        return path, raw, result

    def write_raw(self, path, raw):
        path.write_bytes(gzip.compress(canonical(raw).encode(), mtime=0))

    def dataset(self, arm='F'):
        for i in range(4):
            self.archive(arm, i)
        return self.R.qualify_dataset(arm, self.ledger, self.root)

    def branch(self, arm='F'):
        manifest, pin = self.dataset(arm)
        return self.R.Branch(arm, self.ledger, manifest, pin, updater=self.R.Updater(configuration(arm)),
                             dataset_bytes=(self.root/f'dataset_{arm}.json').read_bytes())

    def synthesize_500(self, branch):
        # Construct checkpoint protocol fixtures, never perform a numerical update.
        initial = len(branch.history)
        for i in range(initial, initial+500):
            batch = branch.index.sample(branch.replay, rng=branch.replay_rng, boundary_rng=branch.boundary_rng)
            branch.history.append(dict(critic_batches=i+1, batch_rows=256, active_rows=256,
                                       episode_count=len(branch.refs), replay_size=len(branch.replay),
                                       critic_sample_sha256=self.R.sample_signature(batch.indices)))
        for opt in branch.updater._optimizers():
            for group in opt.param_groups:
                for parameter in group['params']:
                    opt.state[parameter] = dict(step=torch.tensor(float(initial+500)), exp_avg=torch.zeros_like(parameter),
                                                exp_avg_sq=torch.zeros_like(parameter))
        branch.updater.counts = {key: initial+500 for key in ('critic', 'target', 'actor', 'temperature')}
        self.ledger.state['updates'][branch.arm] = dict(attempted=initial+500, completed=initial+500)

    def test_real_zero_checkpoint_roundtrip_preserves_all_state_without_compute(self):
        branch = self.branch()
        before = branch.capture()
        path = self.root/'zero'
        pin = branch.save(path)
        restored = self.R.restore(path, pin, 'F', self.ledger)
        self.assertTrue(_same(before, restored.capture()))
        self.assertEqual(len(restored.refs), 4)
        self.assertEqual(restored.updater.counts['critic'], 0)

    def test_origin_is_same_zero_state_for_both_permission_modes(self):
        f, s = self.R.zero_updater('F'), self.R.zero_updater('S')
        self.assertTrue(_same(f._snapshot(), s._snapshot()))
        self.assertEqual(f.counts, dict(critic=0, target=0, actor=0, temperature=0))

    def test_rejects_training_denied_or_cross_arm_or_guarded_sources(self):
        for key, value in [('training_admitted', False), ('stage_mode', 'S'), ('optimizer_steps', 500),
                           ('qualification_sha256', 'c'*64)]:
            with self.subTest(key=key):
                self.ledger = Ledger()
                fixtures = [self.archive('F', i) for i in range(4)]
                path, raw, result = fixtures[0]
                raw[key] = value
                self.write_raw(path, raw)
                result['archive_sha256'] = digest(path)
                with self.assertRaises(ValueError):
                    self.R.qualify_dataset('F', self.ledger, self.root)
        self.ledger = Ledger()
        fixtures = [self.archive('F', i) for i in range(4)]
        path, raw, result = fixtures[0]
        raw['guard_facts']['contact_reasons'] = ['FORCE_LIMIT']
        self.write_raw(path, raw)
        result['archive_sha256'] = digest(path)
        with self.assertRaises(ValueError):
            self.R.qualify_dataset('F', self.ledger, self.root)

    def test_requires_four_unique_case_sources(self):
        for i in (0, 1, 2, 2):
            self.archive('F', i)
        with self.assertRaises(ValueError):
            self.R.qualify_dataset('F', self.ledger, self.root)

    def test_checkpoint_cannot_overwrite_existing_committed_directory(self):
        branch = self.branch()
        path = self.root/'saved'
        pin = branch.save(path)
        with self.assertRaises(FileExistsError):
            branch.save(path)
        self.assertEqual(digest(path/'manifest.json'), pin)

    def test_restore_rejects_other_arm_or_authority(self):
        branch = self.branch()
        path = self.root/'saved'
        pin = branch.save(path)
        with self.assertRaises(ValueError):
            self.R.restore(path, pin, 'S', self.ledger)
        self.ledger.state['authorization_sha256'] = 'c'*64
        with self.assertRaises(ValueError):
            self.R.restore(path, pin, 'F', self.ledger)

    def test_online_archive_requires_earned_exact_boundary_and_case_order(self):
        branch = self.branch()
        path, raw, result = self.archive('F', 0, 'online', 500)
        ref = dict(id=raw['episode_id'], path=path.name, sha256=digest(path), role='online')
        with self.assertRaises(ValueError):
            branch.append_archive(ref, path.read_bytes(), 500)
        self.assertEqual(len(branch.refs), 4)
        self.synthesize_500(branch)
        branch.append_archive(ref, path.read_bytes(), 500)
        self.assertEqual(len(branch.refs), 5)
        with self.assertRaises(ValueError):
            branch.append_archive(ref, path.read_bytes(), 500)

    def test_complete_500_can_restore_before_and_after_matching_online_collection(self):
        branch = self.branch()
        self.synthesize_500(branch)
        for label in ('before_online', 'after_online'):
            if label == 'after_online':
                path, raw, _ = self.archive('F', 0, 'online', 500)
                branch.append_archive(dict(id=raw['episode_id'], path=path.name, sha256=digest(path), role='online'),
                                      path.read_bytes(), 500)
            path = self.root/label
            pin = branch.save(path)
            restored = self.R.restore(path, pin, 'F', self.ledger)
            self.assertTrue(_same(branch.capture(), restored.capture()))

    def test_all_registered_boundaries_restore_their_exact_growing_data_prefix(self):
        branch = self.branch('S')
        for block in range(5):
            self.synthesize_500(branch)
            path = self.root/f'boundary_{500*(block+1)}'
            pin = branch.save(path)
            restored = self.R.restore(path, pin, 'S', self.ledger)
            self.assertEqual(len(restored.refs), 4+block)
            self.assertEqual(len(restored.history), 500*(block+1))
            self.assertTrue(_same(restored.capture(), branch.capture()))
            if block < 4:
                source, raw, _ = self.archive('S', block, 'online', 500*(block+1))
                branch.append_archive(dict(id=raw['episode_id'], path=source.name, sha256=digest(source), role='online'),
                                      source.read_bytes(), 500*(block+1))

    def test_restore_zero_rejects_weights_that_do_not_equal_sealed_origin(self):
        branch = self.branch()
        path = self.root/'changed_zero'
        branch.save(path)
        saved = torch.load(path/'state.pt', weights_only=True)
        next(iter(saved['updater']['policy'].values())).view(-1)[0] += 1
        torch.save(saved, path/'state.pt')
        manifest = self.C.read(path/'manifest.json')
        manifest['state_sha256'] = digest(path/'state.pt')
        self.C.write(path/'manifest.json', manifest)
        with self.assertRaises(ValueError):
            self.R.restore(path, digest(path/'manifest.json'), 'F', self.ledger)

    def test_restore_reaudits_replay_and_history_even_after_payload_rehash(self):
        branch = self.branch()
        self.synthesize_500(branch)
        for field in ('replay', 'history', 'rng', 'boundary_index', 'dataset_bytes'):
            with self.subTest(field=field):
                path = self.root/field
                branch.save(path)
                saved = torch.load(path/'state.pt', weights_only=True)
                if field == 'replay': saved['replay']['episodes'][0][1]['rewards'][0] += 1
                elif field == 'history': saved['history'][0]['episode_count'] = 5
                elif field == 'rng': saved['rng']['replay']['state']['state'] += 1
                elif field == 'boundary_index': saved['boundary_index'][branch.refs[0]['id']]['targets'][0] += 1
                else: saved['dataset_bytes'] += b' '
                torch.save(saved, path/'state.pt')
                manifest = self.C.read(path/'manifest.json')
                manifest['state_sha256'] = digest(path/'state.pt')
                self.C.write(path/'manifest.json', manifest)
                with self.assertRaises(ValueError):
                    self.R.restore(path, digest(path/'manifest.json'), 'F', self.ledger)

    def test_failed_update_keeps_attempt_charged_and_releases_meter_context(self):
        branch = self.branch()
        class Meter:
            active = False
            def begin_update(self, token): self.active = True
            def end_context(self): self.active = False
        meter = Meter()
        def fail(*args, **kwargs): raise ValueError('Synthetic update rejection')
        with patch.object(branch.updater, 'update', fail), self.assertRaises(ValueError):
            branch.update_one(meter)
        self.assertEqual(self.ledger.state['updates']['F'], dict(attempted=1, completed=0))
        self.assertFalse(meter.active)
        self.assertEqual(branch.history, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
