"""Recompose stored command states only; never create learning episodes."""
from copy import deepcopy
from pathlib import Path
import gzip,json,sys
import numpy as np
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from small_bound_profile import (outer_contract,compose_small_bound_command,
    audit_action_log,read,sha,ROOT)


def archive_context(raw,index):
    row=raw['transitions'][index];log=row['action_log']
    fields={s['name']:slice(s['start'],s['start']+s['width']) for s in raw['observation_schema']}
    # Use recorded phase and advanced theta, not a re-executed controller.
    phase=raw['trace'][index+1]['policy_phase']
    if log['reference_checked']:phase='SEARCH'
    if log['enabled'] and not log['reference_checked']:phase='INSERT'
    total=np.asarray(log['unfiltered_stage_limited_total'])
    residual=np.asarray(log['applied_residual'])
    # A representative base inside the same stage-limit equivalence class.
    # This cannot recover an unlogged base outside a saturated stage bound.
    base=total-residual
    cfg=read(OUT.parent/'v4_learning_requalification_20261006/configuration.json')['common']['b2_config']
    return dict(base=base.tolist(),phase=phase,enabled=log['enabled'],
        previous_limited=raw['trace'][index]['limited_command_world'],dt=.002,
        reference_xy=log.get('reference_xy_m'),radius=.00012,
        next_theta=log.get('next_search_theta_rad'),search_config=cfg)


def main():
    c=outer_contract();checks=[];n=0;active=0;zero=0
    for name in ['probe_F12p5_aligned','probe_F12p5_y_neg_150']:
        p=OUT.parent/'contact_gate_probe_20261007/run'/(name+'.json.gz')
        r=json.loads(gzip.decompress(p.read_bytes()));matched=0;skipped=[]
        for i,old in enumerate(r['actions']):
            context=archive_context(r,i)
            _,new=compose_small_bound_command(old['actor_action'],context,c)
            # Exact physical semantics, while explicitly changing learning a semantics in memory.
            keys=['requested_residual','applied_residual','stage_limited_total',
                  'predicted_limited_command','zero_residual_limited_command','effective_command_delta']
            if not all(np.allclose(new[k],old[k],rtol=0,atol=1e-15) for k in keys):
                skipped.append(dict(cycle=i,reason='unlogged pre-stage-limit base not recoverable'));continue
            new['actual_end_limited_command']=old['actual_end_limited_command'];audit_action_log(new,c)
            assert new['experience_action']==(old['actor_action'] if old['enabled'] else [0.]*4)
            _,null=compose_small_bound_command([0.]*4,context,c)
            assert np.allclose(null['predicted_limited_command'],old['zero_residual_limited_command'],rtol=0,atol=1e-15)
            matched+=1;n+=1;active+=int(old['enabled']);zero+=1
        checks.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),stored_cycles=len(r['actions']),matched_command_states=matched,skipped_states=skipped))
    result=dict(passed=n>0,matched_command_states=n,active_command_states=active,zero_residual_command_checks=zero,
        sources=checks,new_dynamics=0,new_network_predictions=0,new_optimizer_batches=0,new_published_transitions=0,
        scope='stored command states only; reconstructed representative stage-limited base, not hidden controller provenance or B2 physical trajectory equivalence',
        learning_semantics='unscaled a verified in memory only; historical PC09 actions/files untouched, no converted training archives emitted')
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed proof; do not regenerate')
    (OUT/'command_equivalence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('OFFLINE COMMAND STATES',n,'matched;',sum(len(s['skipped_states']) for s in checks),'not recoverable; no new physics/NN/updates')


if __name__=='__main__':main()
