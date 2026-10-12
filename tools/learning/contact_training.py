"""Bounded contact runner and validation evidence, no automatic physics launch."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import subprocess
import sys
from functools import lru_cache
from .admission import canonical,digest,verify_files
from .admitted_collection import _write_json
from .contact_execution import ContactCollection
from .contact_admission import DELIVERY
from .runtime import ROOT
from .sac_checkpoint import save_checkpoint,capture,validate_state

TEST_PATHS=['tests/learning/test_'+s+'.py' for s in ('contact_execution','admitted_collection','action','observation','sac_collection','sac_checkpoint')]
TEST_EXCLUDE='not loaded_adam_moments_next_updates_match'


@lru_cache(maxsize=1)
def expected_test_ids(source_binding):
    # The cache key binds every test/import; edits invalidate the collection cache.
    command=[sys.executable,'-X','utf8','-B','-m','pytest','-q','-p','no:cacheprovider',
             *TEST_PATHS,'-k',TEST_EXCLUDE,'--collect-only']
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    if result.returncode: raise ValueError('Cannot collect required validation tests')
    ids=sorted(line.replace('/','.').replace('.py::','::') for line in result.stdout.splitlines() if '::test_' in line)
    if not ids or len(ids)!=len(set(ids)): raise ValueError('Invalid required test identities')
    return ids


def verify_validation_evidence(validation):
    if not isinstance(validation,dict) or set(validation)!={'test_binding','synthetic_probe','probe_revalidation','review'}:
        raise ValueError('Complete validation evidence required')
    for name,path in validation.items():
        if not isinstance(path,str) or not (ROOT/path).resolve().is_relative_to(DELIVERY):
            raise ValueError('Validation evidence must be inside delivery')
    binding=json.loads((ROOT/validation['test_binding']).read_text(encoding='utf-8'))
    from tools.validation.verify_residual_interface import all_sources
    if binding['source_sha256']!=all_sources(): raise ValueError('Tests do not bind complete current inputs')
    verify_files(ROOT,binding['source_sha256'])
    report=ROOT/binding['report']
    if digest(report)!=binding['report_sha256'] or binding.get('exit_code')!=0:
        raise ValueError('Unqualified test report')
    cases=list(ET.parse(report).getroot().iter('testcase'))
    ids=[r.attrib['classname']+'::'+r.attrib['name'] for r in cases]
    expected=expected_test_ids(canonical(binding['source_sha256']))
    if not ids or len(ids)!=len(set(ids)) or sorted(ids)!=binding['test_ids'] or sorted(ids)!=expected or any(list(r) for r in cases):
        raise ValueError('Missing, repeated, skipped or failed test coverage')
    probe=json.loads((ROOT/validation['synthetic_probe']).read_text(encoding='utf-8'))
    if (probe.get('physical_episodes')!=0 or probe.get('optimizer_updates')!=3 or
        probe.get('separate_process_equal') is not True or probe.get('all_state_equal') is not True or
        probe.get('configuration')!='contact_four_point_execution_v1'):
        raise ValueError('Complete independent-process synthetic restoration evidence required')
    from .contact_admission import ADDITIONS,MODIFICATIONS
    for path,sha in probe['source_sha256'].items():
        source=DELIVERY/'checks/synthetic_source_snapshot'/path if path in ADDITIONS|MODIFICATIONS else ROOT/path
        if digest(source)!=sha: raise ValueError('Synthetic probe original source changed')
    verify_files(ROOT,probe['artifacts'])
    revalidation=json.loads((ROOT/validation['probe_revalidation']).read_text(encoding='utf-8'))
    if (revalidation.get('source_sha256')!=all_sources() or revalidation.get('checkpoint_read_verified') is not True or
        revalidation.get('optimizer_updates')!=0 or revalidation.get('physical_episodes')!=0 or
        revalidation.get('probe_sha256')!=digest(ROOT/validation['synthetic_probe'])):
        raise ValueError('Current implementation has not revalidated the original synthetic checkpoint')
    review=json.loads((ROOT/validation['review']).read_text(encoding='utf-8'))
    if review.get('unresolved_critical')!=0 or review.get('unresolved_important')!=0:
        raise ValueError('Important review findings remain')


def run_training(chain,output,*,resume=False):
    if not isinstance(chain,ContactCollection): raise TypeError('Contact chain required')
    if type(resume) is not bool: raise TypeError('Explicit boolean resume mode required')
    if resume:
        validate_state(capture(chain),chain.admission)
    elif chain.budget.total or chain.history or chain.collector.attempts or chain.sampler.count:
        raise ValueError('First contact short training must start fresh')
    chain.admission.verify()
    output=Path(output); output.mkdir(parents=True,exist_ok=False)
    checkpoints=[]
    def checkpoint(identity):
        path=output/'checkpoints'/identity
        sha=save_checkpoint(chain,path)
        checkpoints.append(dict(path=path.relative_to(output).as_posix(),sha256=sha,
            audited_total=chain.budget.total,updates=chain.updater.counts['critic']))
        _write_json(output/'checkpoints.json',checkpoints)
        _write_json(output/'run_state.json',dict(status='healthy_boundary',checkpoint=checkpoints[-1]))
    try:
        if resume:
            _write_json(output/'run_state.json',dict(status='updating_restored_boundary'))
            if chain.budget.available: chain.update(chain.budget.available)
            if chain.budget.available: raise RuntimeError('Unconsumed restored credit')
            checkpoint('restored_boundary')
        while chain.budget.total<20000 and chain.sampler.count<6:
            identity=f'contact_{chain.sampler.count:06d}'
            _write_json(output/'run_state.json',dict(status='running',episode_id=identity))
            chain.start(identity)
            while chain.collector.active: chain.collect(500)
            if chain.budget.available: chain.update(chain.budget.available)
            if chain.budget.available: raise RuntimeError('Unconsumed update credit')
            checkpoint(identity)
        result=dict(training_completed=chain.budget.total>=20000,attempts=chain.sampler.count,
            audited_total=chain.budget.total,updates=chain.updater.counts,final_checkpoint=checkpoints[-1],
            stop_reason='target_met' if chain.budget.total>=20000 else 'six_attempt_limit')
        _write_json(output/'training.json',result)
        _write_json(output/'run_state.json',dict(status='completed',checkpoint=checkpoints[-1]))
        return result
    except BaseException as exc:
        chain.fail(exc)
        _write_json(output/'run_state.json',dict(status='failed',error=repr(exc)))
        _write_json(output/'failure.json',dict(error=repr(exc),checkpoints=checkpoints))
        raise
    finally:
        _write_json(output/'attempts.json',chain.collector.attempts)
        _write_json(output/'updates.json',chain.history)


def validate_resume_source(path,sha):
    """CLI cannot roll back a later failed/in-flight attempt to erase its budget."""
    path=Path(path).resolve();source=path.parent.parent
    state=json.loads((source/'run_state.json').read_text(encoding='utf-8'))
    checkpoints=json.loads((source/'checkpoints.json').read_text(encoding='utf-8'))
    if (state.get('status') not in ('healthy_boundary','completed') or not checkpoints or
        state.get('checkpoint')!=checkpoints[-1] or checkpoints[-1]['sha256']!=sha or
        (source/checkpoints[-1]['path']).resolve()!=path or (source/'failure.json').exists()):
        raise ValueError('Only the latest durable healthy boundary can resume; failed/in-flight runs cannot retry')
