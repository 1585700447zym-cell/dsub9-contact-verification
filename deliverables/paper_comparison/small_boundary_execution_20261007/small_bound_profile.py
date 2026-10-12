"""F12p5 action semantics and raw audit. Importing constructs no learner/env."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import hashlib, json, math, sys
import numpy as np

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
REG=OUT.parent/'small_boundary_registration_20261007'
REG_SEAL='685f844ed027ebe7a00d243f1195d41b16772d42cc45d47b92ba93b1c06473ae'
SCALE=[12.5e-6,12.5e-6,.000125,.000125]


def canonical(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))


def registration():
    if sha(REG/'delivery_manifest.json')!=REG_SEAL:raise ValueError('PC11 seal differs')
    manifest=read(REG/'delivery_manifest.json')
    pin=manifest['files']['draft_contract.json']['sha256']
    if sha(REG/'draft_contract.json')!=pin:raise ValueError('Registration changed')
    return read(REG/'draft_contract.json')


def outer_contract():
    from tools.learning.v4_pilot_contract import learning_config
    r=registration();p=r['groups']['F12p5']
    return dict(version='pc12_small_bound_outer_contract_v1',profile='F12p5',
        registration_sha256=sha(REG/'draft_contract.json'),common_key=r['common_key'],
        physical_scale_SI=p['action_scale_SI'],normalized_bounds=p['normalized_action_bounds'],
        replay_action=p['replay_action'],physical_request=p['physical_request'],
        engine_mode='F50',engine_nominal_scale_role='numeric configuration identity only',
        engine_config_sha256=digest(learning_config('F50')),observation_width=137,
        learning=p['learning'],warmup=p['warmup'],online=p['online'],zero_origin=p['zero_origin'],
        reference_filter='residual_reference_continuation_v2')


def profile_digest(contract):return digest(contract)


def validate_outer_contract(contract):
    if not isinstance(contract,dict) or canonical(contract)!=canonical(outer_contract()):
        raise ValueError('Complete registered F12p5 outer contract required')
    return profile_digest(contract)


def decorate_action_log(log,action,context,contract):
    from tools.learning.action import normalized_action
    pin=validate_outer_contract(contract);a=normalized_action(action)
    if type(log['enabled']) is not bool:raise ValueError('Boolean permission required')
    result=deepcopy(log)
    result.update(raw_action=a.tolist(),experience_action=(a if log['enabled'] else np.zeros(4)).tolist(),
                  compositor_action=(a*.25).tolist(),profile_sha256=pin,
                  small_bound_context=deepcopy(context))
    return result


def compose_small_bound_command(action,context,contract):
    from tools.learning.action import normalized_action
    from tools.learning.v4_continuation import compose_continuation_command
    validate_outer_contract(contract);a=normalized_action(action);c=deepcopy(context)
    if c.get('dt')!=.002 or type(c.get('enabled')) is not bool:
        raise ValueError('Frozen control period and boolean permission required')
    if c['enabled'] and c['phase'] not in ('INSERT','SEARCH'):
        raise ValueError('F12p5 permission only INSERT/SEARCH')
    if c.get('search_config') is not None:c['search_config']=SimpleNamespace(**c['search_config'])
    command,log=compose_continuation_command(action=(a*.25).tolist(),**c)
    return command,decorate_action_log(log,a,context,contract)


def audit_action_log(log,contract):
    pin=validate_outer_contract(contract)
    try:
        if log['profile_sha256']!=pin:raise ValueError('Action profile differs')
        _,expected=compose_small_bound_command(log['raw_action'],log['small_bound_context'],contract)
        for k,v in expected.items():
            actual=log[k]
            if isinstance(v,list):
                if np.asarray(actual).shape!=np.asarray(v).shape or not np.allclose(actual,v,rtol=0,atol=1e-15):
                    raise ValueError('Action/physical command differs: '+k)
            elif canonical(actual)!=canonical(v):raise ValueError('Action context differs: '+k)
        if 'actual_end_limited_command' in log and not np.allclose(
                log['actual_end_limited_command'],expected['predicted_limited_command'],rtol=0,atol=1e-15):
            raise ValueError('Executed command differs from prediction')
    except (KeyError,TypeError,OverflowError) as exc:
        raise ValueError('Incomplete small-bound action archive') from exc
    return True


def validate_transition_protocol(rows):
    """Pre-admission raw checks; do not import the torch-backed replay container.

    The original V4Replay._prepare is still mandatory in the admitted core.
    This independent gate permits auditing witnesses before runtime imports.
    """
    from tools.learning.action import normalized_action
    from tools.learning.v4_pilot_contract import permission
    previous=None
    for i,row in enumerate(rows):
        for key in ('terminated','truncated','action_active','next_action_active'):
            if type(row[key]) is not bool:raise ValueError('Boolean transition flag required')
        if row['truncated'] or row['terminated']!=(i==len(rows)-1):raise ValueError('Single complete terminal required')
        obs,nxt=[np.asarray(row[k],dtype=float) for k in ('observation','next_observation')]
        if any(x.shape!=(137,) or not np.isfinite(x).all() or np.max(np.abs(x))>10 for x in (obs,nxt)):
            raise ValueError('Finite bounded 137D observations required')
        if permission(obs,'F50')!=row['action_active'] or permission(nxt,'F50')!=row['next_action_active']:
            raise ValueError('Observation-derived permission differs')
        if previous is not None and (not np.array_equal(previous[0],obs) or previous[1]!=row['action_active']):
            raise ValueError('Discontinuous episode')
        a=normalized_action(row['action'])
        if not row['action_active'] and np.any(a):raise ValueError('Inactive replay action must be zero')
        dt=row['dt'];g=row['discount'];r=row['reward']
        if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in (dt,g,r)) or dt<=0 or not math.isclose(g,math.exp(-dt/10),abs_tol=1e-12,rel_tol=0):
            raise ValueError('Finite reward and physical-time discount required')
        if i==len(rows)-1 and row['next_action_active']:raise ValueError('Terminal next action must be inactive')
        previous=nxt,row['next_action_active']


def audit_small_bound_episode(raw,contract):
    """Action/reward/transcript audit; core publication also audits stop/eligibility."""
    pin=validate_outer_contract(contract)
    try:
        if (raw['physical_profile']!='F12p5' or raw['profile_sha256']!=pin or
            canonical(raw['outer_contract'])!=canonical(contract) or raw['mode']!='F50' or
            raw['comparison_key']!=contract['common_key']):raise ValueError('Outer episode identity differs')
        rows=raw['transitions']
        if not 0<len(rows)<=14500 or len(raw['trace'])!=len(rows)+1 or len(raw['actions'])!=len(rows):
            raise ValueError('Complete bounded physical transcript required')
        from tools.learning.reward import EpisodeReward
        validate_transition_protocol(rows)
        reward=EpisodeReward(.004)
        for i,row in enumerate(rows):
            log=row['action_log'];audit_action_log(log,contract)
            if (log!=raw['actions'][i] or row['trace_row']!=raw['trace'][i+1] or
                log['enabled'] is not row['action_active'] or row['action']!=log['experience_action']):
                raise ValueError('Action/experience/transcript differs')
            if not np.allclose(log['actual_end_limited_command'],row['trace_row']['limited_command_world'],rtol=0,atol=1e-15):
                raise ValueError('Executed command differs from physical trace')
            if rows[-1]['terminated'] is not True or rows[-1]['truncated'] is not False:
                raise ValueError('Natural final terminal required')
            parts=reward.advance(advance_m=row['advance_m'],dt=row['dt'],force_N=row['cycle_force_N'],torque_G_Nm=row['cycle_torque_G_Nm'])
            parts['terminal']=reward.finalize(raw['outcome']['task_outcome']) if i==len(rows)-1 else 0.
            parts['total']+=parts['terminal']
            if parts.keys()!=row['reward_terms'].keys() or any(not math.isclose(v,row['reward_terms'][k],abs_tol=1e-12,rel_tol=0) for k,v in parts.items()) or not math.isclose(parts['total'],row['reward'],abs_tol=1e-12,rel_tol=0):
                raise ValueError('Episode reward differs')
    except (KeyError,TypeError,OverflowError) as exc:
        raise ValueError('Incomplete outer physical archive') from exc
    return dict(profile_sha256=pin,cycles=len(rows),audit='action/reward/commands; physical stop still requires core audit')


def __getattr__(name):
    if name=='SmallBoundSession':
        from small_bound_session import SmallBoundSession
        return SmallBoundSession
    raise AttributeError(name)
