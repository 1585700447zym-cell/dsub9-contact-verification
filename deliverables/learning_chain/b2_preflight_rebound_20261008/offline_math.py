"""Load explicitly selected, pinned numerical definitions without engine imports.

The geometry module normally imports a validation runner (and MuJoCo). Only its
pure definitions are compiled here. Model geometry comes from the same XML and
frozen referee metadata. No simulator/session/class constructor is selected.
"""
import ast
import __future__
from copy import deepcopy
from functools import lru_cache
import math
from types import SimpleNamespace
import xml.etree.ElementTree as ET
from scope_contract import ROOT,read,sha,proposal


@lru_cache(maxsize=1)
def numerics():
    import numpy as np
    pins=read(ROOT/'deliverables/paper_comparison/small_boundary_numeric_execution_20261008/prior_source_bindings.json')['production_inputs']
    ns=dict(np=np,math=math,deepcopy=deepcopy)
    def load(name,names):
        path=ROOT/name
        if sha(path)!=pins[name]:raise ValueError('Pinned numerical source differs: '+name)
        tree=ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
        selected=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
        if {n.name for n in selected}!=set(names):raise ValueError('Numerical definition missing')
        # The only internal import is actual_stop_pass -> physical_tail_pass,
        # injected from its pinned definition below to avoid engine import.
        for node in selected:
            if node.name=='actual_stop_pass':
                node.body=[n for n in node.body if not isinstance(n,ast.ImportFrom)]
        exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec',
                     flags=__future__.annotations.compiler_flag),ns)
    load('tools/dynamics/safety.py',['_finite_vector','limit_command'])
    ns['DEFAULT_ACTION_SCALE']=(.00015,.00015,.005,.005)
    load('tools/learning/action.py',['validated_action_scale','normalized_action','map_residual','_stage_limit','compose_command'])
    ns.update(SCALE=(.00005,.00005,.0005,.0005),VELOCITY=[.001]*3+[.03]*3,
              ACCELERATION=[.005]*3+[.3]*3,TOLERANCE_M=1e-12)
    load('tools/learning/v4_action.py',['ReferenceEnvelopeInfeasible','compose_reference_command'])
    ns['VERSION']='residual_reference_continuation_v2'
    load('tools/learning/v4_continuation.py',['predict_next_search','compose_continuation_command'])
    load('tools/learning/reward.py',['EpisodeReward'])
    observation_path=ROOT/'tools/learning/observation.py'
    if sha(observation_path)!=pins['tools/learning/observation.py']:raise ValueError('Observation source changed')
    constants={'POLICY_PHASES','PHYSICAL_PHASES','RECOVERY_PHASES','DECISIONS','GUARDS','VECTOR_WIDTHS'}
    tree=ast.parse(observation_path.read_text(encoding='utf-8-sig'))
    definitions=[node for node in tree.body if isinstance(node,ast.Assign)
                 and any(isinstance(t,ast.Name) and t.id in constants for t in node.targets)]
    exec(compile(ast.Module(body=definitions,type_ignores=[]),str(observation_path),'exec'),ns)
    load('tools/learning/observation.py',['rotation_vector_world','ObservationBuilder'])
    load('tools/learning/v4_observation.py',['V4ObservationBuilder'])
    load('tools/learning/outcome.py',['classify_outcome'])
    load('tools/validation/run_contact_candidate_stop.py',['physical_tail_pass'])
    load('tools/validation/native313_matrix_audit.py',['actual_stop_start','samples_finite','actual_stop_pass'])
    model=ROOT/'models/dsub9_pair.xml'
    if sha(model)!=pins['models/dsub9_pair.xml']:raise ValueError('Referee XML changed')
    xml=ET.parse(model).getroot();pins_xml=xml.findall('.//geom[@class="pin_collision"]')
    common=read(ROOT/proposal()['parent']['configuration'])['common'];meta=common['geometry_referee']
    angles=np.arange(meta['segments'])*2*math.pi/meta['segments']
    ns.update(_pin_centers=np.array([[float(v) for v in p.get('pos').split()] for p in pins_xml]),
        _pin_sizes=np.array([[float(v) for v in p.get('size').split()] for p in pins_xml]),
        _holes=np.array([[float(v) for v in p.get('pos').split()] for p in xml.findall('.//geom[@type="sdf"]')]),
        _normals=np.c_[np.cos(angles),np.sin(angles),np.zeros(meta['segments'])],
        _LAYERS=[(r['name'],r['radius_m'],r['z0_m'],r['z1_m']) for r in meta['layers']],
        GEOMETRY_TOLERANCE_M=meta['tolerance_m'])
    load('tools/model/layered_task.py',['_boundary_angles','_layer_margin','_pose','layered_pin_clearance_m','layered_pin_fit','functional_finish'])
    return ns
