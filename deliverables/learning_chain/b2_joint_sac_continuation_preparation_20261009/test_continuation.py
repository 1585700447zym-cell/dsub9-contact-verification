"""Contract counterexamples use only stdlib and frozen metadata."""
import copy, importlib, json, sys, unittest, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HERE / 'continuation_contract.py').exists(), 'Missing trainable continuation contract')
        self.c = importlib.import_module('continuation_contract')
        self.spec = json.loads((HERE / 'input_spec.json').read_bytes())
        self.binding = dict(mode='F50', purpose='bounded_physical_pilot', qualification_sha256='a' * 64,
                            config_sha256=self.spec['legacy_config_sha256'])

    def test_remaining_schedule_has_no_repeat_of_initial_or_warmup(self):
        p = self.c.remaining_schedule()
        self.assertEqual([r['stage'] for r in p], ['online'] * 4 + ['final'] * 4 + ['restore'])
        self.assertEqual([r['optimizer_steps'] for r in p], [0, 500, 1000, 1500] + [2000] * 5)

    def test_legacy_grant_never_becomes_new_admission(self):
        old = copy.deepcopy(self.binding); old['qualification_sha256'] = self.spec['source_grant_sha256']
        with self.assertRaises(ValueError): self.c.require_new_binding(old, self.spec)

    def test_only_pinned_old_warm_archive_uses_legacy_binding(self):
        raw = dict(stage='warmup', case_index=0, episode_id='warmup_F50_J01')
        old = self.c.archive_binding(raw, self.binding, self.spec, self.spec['warmup'][0]['archive_sha256'])
        self.assertEqual(old['qualification_sha256'], self.spec['source_grant_sha256'])
        for bad in (None, '0' * 64):
            with self.assertRaises(ValueError): self.c.archive_binding(raw, self.binding, self.spec, bad)

    def test_online_archive_must_use_new_qualification(self):
        raw = dict(stage='online', case_index=0, episode_id='online_F50_J01')
        self.assertEqual(self.c.archive_binding(raw, self.binding, self.spec), self.binding)
        with self.assertRaises(ValueError): self.c.archive_binding(dict(raw, stage='zero'), self.binding, self.spec)

    def test_wrong_warm_case_or_id_is_refused(self):
        for raw in (dict(stage='warmup', case_index=1, episode_id='warmup_F50_J01'),
                    dict(stage='warmup', case_index=True, episode_id='warmup_F50_J02')):
            with self.assertRaises(ValueError): self.c.archive_binding(raw, self.binding, self.spec, self.spec['warmup'][0]['archive_sha256'])

    def execution(self):
        self.assertTrue((HERE / 'execution.py').exists(), 'Missing continuation admission and ledger')
        return importlib.import_module('execution')

    def test_counter_refuses_overrun_and_closed_reuse(self):
        e = self.execution()
        with tempfile.TemporaryDirectory(dir=HERE) as d:
            counter = e.Counter.create(Path(d) / 'counter.json', {'formal_updates': 2})
            counter.take('formal_updates', 2)
            for n in (1, True, 0, -1):
                with self.assertRaises((RuntimeError, ValueError)): counter.take('formal_updates', n)
            counter.close(owned_exit_confirmed=True)
            with self.assertRaises((RuntimeError, PermissionError)): counter.take('formal_updates')

    def test_old_actual_grants_cannot_start_new_candidate(self):
        e = self.execution()
        old = json.loads((HERE.parent / 'b2_joint_sac_execution_20261009/execution/grant.json').read_bytes())
        from joint_contract import digest
        with self.assertRaises(PermissionError): e.verify_grant({}, old, digest(old), 'b' * 64)

    def test_role_claim_cannot_repeat_even_before_runtime(self):
        e = self.execution()
        with tempfile.TemporaryDirectory(dir=HERE) as d:
            counter = e.Counter.create(Path(d) / 'counter.json', {'formal_updates': 2})
            counter.claim('reader', 'warm')
            with self.assertRaises(PermissionError): counter.claim('reader', 'warm')
            with self.assertRaises(PermissionError): counter.claim('reader', 'zero')

    def test_migration_only_changes_binding_and_preserves_source(self):
        old = dict(version='v4_pilot_checkpoint_v1', binding=dict(self.binding, qualification_sha256=self.spec['source_grant_sha256']),
                   config={}, archives={x['id']: b'data' for x in self.spec['warmup']},
                   attempts=[dict(episode_id=x['id'], stage='warmup', case_index=i) for i, x in enumerate(self.spec['warmup'])],
                   updater=dict(counts=dict(critic=0, actor=0, temperature=0, target=0)),
                   history=[], update_attempts=0, journal='', stop_reason=None, replay=dict(size=19300), warm=dict(draws=388, held=[0.] * 4))
        envelope = dict(version='b2_archived_warm_checkpoint_v1', training_admitted=False,
                        provenance=dict(input_spec_sha256=self.c.original_spec_digest(self.spec), binding_sha256=self.c.restoration_binding_pin(self.spec),
                                        source_grant_sha256=self.spec['source_grant_sha256'], source_zero_sha256=self.spec['zero_state_sha256'],
                                        boundary=self.spec['source_boundary'], old_run_remains_closed=True), state=old, boundary={})
        before = copy.deepcopy(envelope)
        migrated = self.c.migrate_warm_state(envelope, self.binding, self.spec)
        self.assertEqual(envelope, before)
        self.assertEqual(migrated, dict(old, binding=self.binding))
        for field, value in [('training_admitted', True), ('version', 'wrong')]:
            bad = copy.deepcopy(envelope); bad[field] = value
            with self.assertRaises(ValueError): self.c.migrate_warm_state(bad, self.binding, self.spec)
        for field, value in [('update_attempts', 1), ('journal', 'unresolved'), ('stop_reason', 'failure')]:
            bad = copy.deepcopy(envelope); bad['state'][field] = value
            with self.assertRaises(ValueError): self.c.migrate_warm_state(bad, self.binding, self.spec)

if __name__ == '__main__': unittest.main(verbosity=2)
