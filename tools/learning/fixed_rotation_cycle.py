"""One approved fixed-rotation candidate, with inherited immutable evidence."""
from copy import deepcopy
from pathlib import Path
from .runtime import ROOT, select_runtime, active_package
from .admission import canonical, digest, verify_files
from .admitted_collection import _write_json
from .bounded_contact import BoundedAdmission, BoundedUpdater, RunLedger, bounded_config, current_sources, validate_case
from .repaired_cycle import read, pinned_manifest, RETRY_BINDING_PIN

DELIVERY=ROOT/'deliverables/learning_chain/b2_fixed_rotation_cycle_20260928'
PREVIOUS=ROOT/'deliverables/learning_chain/b2_repaired_cycle_v2_20260928'
OLD=ROOT/'deliverables/learning_chain/b2_bounded_cycle_20260927'
CONFIG=ROOT/'docs/stage_b/四点接触固定转动配置_v1.json'
PARENT_PIN='31815c4a9a12f97a784537e00d2ebceb8d8e6860089cf5f09188bc926d79052e'
PREVIOUS_FILES_PIN='be95c411bbb384497bf8021d49f01dad2f6c6cda3dea403510ea2a20e9481476'
SNAPSHOTS_PIN='1dd3fd09692bf8ee03d3010829ca6b4f5e496f532a6d53a43673251848ed76aa'


def fixed_config():
    config=bounded_config();config['version']='fixed_rotation_cycle_v1'
    config['action']['scale']=[.00015,.00015,.0005,.0005]
    return config


def validate_fixed_config(config):
    if canonical(config)!=canonical(fixed_config()):raise ValueError('Unapproved fixed rotation configuration')


def fixed_sources():
    result=current_sources();result[CONFIG.relative_to(ROOT).as_posix()]=digest(CONFIG)
    result.update(verify_supervisor_sources())
    return result


def verify_supervisor_sources():
    binding=pinned_manifest(OLD/'retry_01/binding.json',RETRY_BINDING_PIN)
    verify_files(ROOT,binding['files'])
    names=[(OLD/'retry_01'/name).relative_to(ROOT).as_posix() for name in ('driver.py','test_driver.py')]
    return {name:binding['files'][name] for name in names}


def verify_parent_sources(parent,snapshots):
    for name,expected in parent['source_sha256'].items():
        if digest(ROOT/snapshots.get(name,name))!=expected:raise ValueError('Parent source changed: '+name)


def verify_previous():
    verify_supervisor_sources()
    parent=pinned_manifest(PREVIOUS/'admission.json',PARENT_PIN)
    snapshots=pinned_manifest(DELIVERY/'parent_source_snapshots.json',SNAPSHOTS_PIN)
    verify_parent_sources(parent,snapshots)
    verify_files(ROOT,parent['evidence_sha256'])
    verify_files(ROOT,pinned_manifest(DELIVERY/'previous_files.json',PREVIOUS_FILES_PIN))
    prior=read(PREVIOUS/'run/cumulative_budget.json')
    if (prior['cumulative_dynamic_starts']!=27 or
        read(PREVIOUS/'run/training_episodes/update_budget.json')['attempted']!=3000 or
        read(PREVIOUS/'process_exit.json')['returncode']!=1):raise ValueError('Prior stopped attempt accounting changed')
    return parent


def validate_record(record):
    if (record.get('capability')!='fixed_rotation_cycle_v1' or record.get('synthetic_only') is not False or
        record.get('parent_admission_sha256')!=PARENT_PIN or
        any(record.get(k) is not True for k in ('collection_admitted','update_admitted','restore_admitted'))):
        raise ValueError('Fixed rotation execution qualification required')
    validate_fixed_config(record['config'])


class FixedUpdater(BoundedUpdater):
    config_validator=staticmethod(validate_fixed_config)


class FixedAdmission(BoundedAdmission):
    updater_type=FixedUpdater

    def verify(self,case=None):
        if self.path.resolve()!=(DELIVERY/'admission.json').resolve() or digest(self.path)!=self.expected_digest:
            raise ValueError('Fixed rotation admission pin/path changed')
        record=read(self.path);validate_record(record)
        parent=verify_previous()
        if record['source_sha256']!=fixed_sources():raise ValueError('Current fixed rotation source changed')
        verify_files(ROOT,record['evidence_sha256'])
        select_runtime(PREVIOUS/'runtime.json',expected_digest=parent['runtime_record_sha256'])
        from tools.validation.verify_residual_interface import qualified_runtime
        if canonical(qualified_runtime(active_package()))!=canonical(parent['runtime']):
            raise ValueError('Runtime differs from reused B2 baseline')
        if case is not None:validate_case(case)
        self._record=record;return deepcopy(record)


def accounting(state):
    n=state['dynamic_starts']
    if type(n) is not int or not 0<=n<=32 or len(state['attempts'])!=n:
        raise ValueError('Invalid fixed rotation cumulative budget')
    return dict(previous_dynamic_starts=27,new_dynamic_starts=n,cumulative_dynamic_starts=27+n,
        new_dynamic_cap=32,cumulative_cap=59,formal_update_cap=4500,previous_formal_updates=3000,
        automatic_retry=False,old_remaining_budget_retired=True)


class FixedLedger(RunLedger):
    def start(self,stage,identity):
        accounting(self.state)
        if stage not in self.CAPS:raise RuntimeError('Unknown fixed rotation stage')
        for earlier in list(self.CAPS)[:list(self.CAPS).index(stage)]:
            rows=[r for r in self.state['attempts'] if r['stage']==earlier]
            if len(rows)!=self.CAPS[earlier] or any(r['status']!='finished' for r in rows):
                raise RuntimeError('Prior fixed rotation stage incomplete: '+earlier)
        super().start(stage,identity)
        _write_json(self.path.parent/'cumulative_budget.json',accounting(self.state))


def reuse_baseline(run):
    receipt=read(DELIVERY/'baseline_reuse.json')
    if receipt.get('passed') is not True:raise ValueError('Zero B2 reuse was not qualified')
    verify_files(ROOT,receipt['input_sha256'])
    output=Path(run)/'baseline';output.mkdir(exist_ok=False)
    _write_json(output/'results.json',read(PREVIOUS/'run/baseline/results.json'))
    _write_json(output/'reuse.json',receipt)
