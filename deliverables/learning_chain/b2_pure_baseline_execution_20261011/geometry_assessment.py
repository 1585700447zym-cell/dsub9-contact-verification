"""Recalculate saved-pose clearance with frozen referee; all physics calls blocked."""
import gzip
import importlib.abc
import json
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PREP = ROOT / 'deliverables/learning_chain/b2_pure_baseline_preparation_20261011'
sys.path.insert(0, str(PREP)); sys.path.insert(0, str(ROOT))
import contract as c


class NoLearning(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('torch', 'stable_baselines3'):
            raise AssertionError('No learned runtime in saved-pose geometry analysis')


sys.meta_path.insert(0, NoLearning())
binding, config = c.verify_binding()
c.check_runtime(binding['numerical_runtime'], check_interpreter=True)
assessment = c.read(OUT / 'assessment.json')
assert assessment['status'].startswith('CLOSED_')
assert not (OUT / 'geometry_assessment.json').exists()
from tools.learning.runtime import select_runtime, verify_runtime, active_package
select_runtime(binding['runtime_record'], expected_digest=binding['runtime_record_sha256'])
assert c.digest(verify_runtime(active_package())) == config['common']['runtime_proof_sha256']
import mujoco


def reject_physics(*args, **kwargs):
    raise AssertionError('Saved-pose calculation must not create or advance a physical model')


for name in ('MjModel', 'MjData', 'mj_step', 'mj_step1', 'mj_step2', 'mj_forward', 'mj_resetData'):
    setattr(mujoco, name, reject_physics)
from tools.model.layered_task import referee_metadata, layered_pin_clearance_m
assert referee_metadata() == config['common']['geometry_referee']
rows = []
for record in assessment['records']:
    path = Path(record['archive_path']); assert c.sha(path) == record['sha256']
    raw = json.loads(gzip.decompress(path.read_bytes()))
    task_index = min(range(len(raw['trace'])), key=lambda i: abs(raw['trace'][i]['time_s'] - raw['task_end_time_s']))
    task_margin = layered_pin_clearance_m(raw['trace'][task_index])
    final_margin = layered_pin_clearance_m(raw['trace'][-1])
    rows.append(dict(role=record['role'], case_id=record['case_id'], archive_sha256=record['sha256'],
        task_end_clearance_um=task_margin * 1e6, audit_end_clearance_um=final_margin * 1e6,
        audit_end_geometry_fit=final_margin >= -config['common']['geometry_referee']['tolerance_m']))
c.verify_binding()
c.write(OUT / 'geometry_assessment.json', dict(version='saved_pose_layered_clearance_v1', assessed_at=c.now(),
    rows=rows, referee=config['common']['geometry_referee'], source_binding_sha256=c.sha(PREP / 'source_binding.json'),
    code_sha256=c.sha(OUT / 'geometry_assessment.py'), new_physical_models=0, new_physical_steps=0,
    new_policy_calls=0, new_tensor_loads=0, new_training_updates=0,
    meaning='Minimum frozen cylinder/layer tangent-plane clearance over all nine pins at the saved pose; positive is geometric fit margin. Does not re-run dynamics or the continuous success hold.'))
print(json.dumps(rows, ensure_ascii=False))
