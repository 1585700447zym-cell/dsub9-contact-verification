"""PC-09 deployment profiles; explicit new permission contract, never training."""
import math
import numpy as np
from tools.learning.v4_pilot_contract import field_slices
from tools.learning.v4_continuation import ContinuationResidualSession

PROFILES=('B2','F50','F12.5','G50')
FORCE_SCALE_N=.025
THRESHOLD_N=.005

def check_profile(profile):
    if profile not in PROFILES:raise ValueError('Registered PC-09 profile required')

def enabled(profile,phase,base,wrench_z):
    check_profile(profile)
    if not math.isfinite(wrench_z):raise ValueError('Finite sensed axial force required')
    if phase not in ('INSERT','SEARCH') or not base:return False
    measured=np.float32(np.clip(wrench_z/FORCE_SCALE_N,-10.,10.))
    return bool(profile!='G50' or phase=='SEARCH' or measured<=np.float32(-THRESHOLD_N/FORCE_SCALE_N))

def permissions(observations,profile):
    """Validate original structural guards, then the declared deployment rule."""
    check_profile(profile);o=np.asarray(observations);single=o.ndim==1
    if single:o=o.reshape(1,-1)
    if o.ndim!=2 or o.shape[1]!=137 or not len(o) or o.dtype.kind not in 'iuf' or not np.isfinite(o).all() or np.max(np.abs(o))>10:
        raise ValueError('Finite bounded 137D observations required')
    s=field_slices()
    for name in ('policy_phase','physical_phase','recovery_phase','decision'):
        a=o[:,s[name]]
        if not np.isin(a,(0.,1.)).all() or not np.all(a.sum(axis=1)==1):raise ValueError('Invalid one-hot '+name)
    for name in s:
        if name.endswith('_valid') or name in ('pending','action_active','simulation_valid','invalid_latched','latched_guards','reference_release_pending'):
            if not np.isin(o[:,s[name]],(0.,1.)).all():raise ValueError('Invalid boolean '+name)
    pending=o[:,s['pending']][:,0].astype(bool)
    if np.any(pending!=(o[:,s['decision']][:,0]==0)):raise ValueError('Decision/pending mismatch')
    phase=np.argmax(o[:,s['policy_phase']],axis=1);allowed=(phase==0)|(phase==2)
    if profile=='G50':
        z=o[:,s['wrench_history_M'].start+2].astype(np.float32)
        allowed=(phase==2)|((phase==0)&(z<=np.float32(-THRESHOLD_N/FORCE_SCALE_N)))
    expected=allowed & (o[:,s['physical_phase']][:,0]==1) & ~pending & (o[:,s['simulation_valid']][:,0]==1)
    expected &= ~o[:,s['latched_guards']].any(axis=1) & ~o[:,s['invalid_latched']].any(axis=1)
    if np.any(o[:,s['action_active']][:,0]!=expected):raise ValueError('PC-09 same-cycle permission mismatch')
    return bool(expected[0]) if single else expected

def deployment_action(actor_action,profile):
    check_profile(profile);a=np.asarray(actor_action,dtype=float)
    if a.shape!=(4,) or not np.isfinite(a).all() or np.any(np.abs(a)>1):raise ValueError('Finite normalized original actor action required')
    return np.zeros(4) if profile=='B2' else a.copy()*(.25 if profile=='F12.5' else 1.)

class ProfileSession(ContinuationResidualSession):
    def __init__(self,*,profile,**kwargs):
        check_profile(profile);self.profile=profile
        if kwargs.get('mode')!='F50':raise ValueError('Original session compositor must remain F50')
        super().__init__(**kwargs)

    def stage_permission(self,phase,base_enabled):
        wrench=np.asarray(self._cache.state['contact_wrench_M'],dtype=float)
        if wrench.shape!=(6,) or not np.isfinite(wrench).all():raise ValueError('Visible wrench required')
        return enabled(self.profile,phase,base_enabled,float(wrench[2]))

def audit_rows(raw):
    profile=raw['profile'];check_profile(profile)
    if raw['mode']!=profile or raw['scope']!='contact_gate_deployment_probe':raise ValueError('Profile/scope mislabel')
    rows=raw['transitions'];logs=raw['actions']
    if not rows or len(rows)!=len(logs):raise ValueError('Complete aligned rows required')
    observations=np.asarray([t['observation'] for t in rows]);next_observations=np.asarray([t['next_observation'] for t in rows])
    active=permissions(observations,profile);next_active=permissions(next_observations,profile)
    previous=None
    for i,(t,log) in enumerate(zip(rows,logs)):
        if t['action_log']!=log or any(type(t[k]) is not bool for k in ('action_active','next_action_active','terminated','truncated')):
            raise ValueError('Logs or boundary flags differ')
        if bool(active[i])!=t['action_active'] or bool(next_active[i])!=t['next_action_active'] or log['enabled']!=t['action_active']:
            raise ValueError('Profile mask differs')
        if previous is not None and (not np.array_equal(previous[0],observations[i]) or previous[1]!=bool(active[i])):
            raise ValueError('Discontinuous observations/masks')
        if t['truncated'] or t['terminated']!=(i==len(rows)-1) or (t['terminated'] and next_active[i]):raise ValueError('Single final boundary required')
        actor=np.asarray(log['actor_action'],dtype=float);request=deployment_action(actor,profile)
        if (not active[i] or profile=='B2') and np.any(actor!=0):raise ValueError('Inactive/B2 actor request must be zero')
        if any(not np.array_equal(np.asarray(v),request) for v in (t['action'],log['raw_action'],log['experience_action'])):
            raise ValueError('Actor output/deployment request mapping differs')
        dt=t['dt'];g=t['discount']
        if not math.isfinite(dt) or dt<=0 or not math.isfinite(g) or not math.isclose(g,math.exp(-dt/10),abs_tol=1e-12,rel_tol=0):
            raise ValueError('Physical-time discount differs')
        previous=next_observations[i],bool(next_active[i])
    calls=0 if profile=='B2' else int(active.sum())
    if type(raw['policy_calls']) is not int or raw['policy_calls']!=calls or raw['policy_call_attempts']!=calls:
        raise ValueError('Actual frozen network calls differ')
    return dict(rows=len(rows),network_policy_calls=calls,training_admitted=False,published_transitions=0)
