"""Offline original-archive audit; no physical or neural execution."""
import argparse,gzip,json,os,sys
from copy import deepcopy
import numpy as np
import night_contract as N
from run_evaluation import select_runtime,equal_trace,collector_output

def audit(variant):
    select_runtime()
    import torch,mujoco
    calls=dict(model=0,optimizer=0,physics=0)
    def forbidden(kind):
        def fail(*a,**k):calls[kind]+=1;raise RuntimeError('Offline audit forbids '+kind)
        return fail
    torch.nn.Module._call_impl=forbidden('model');torch.optim.Adam.step=forbidden('optimizer')
    for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):setattr(mujoco,name,forbidden('physics'))
    from frozen_reader import load
    from tools.learning.sac_checkpoint import _audit_physics,_same
    from tools.learning.engineering_evaluation import episode_metrics
    from tools.learning.audited_replay import AuditedReplay
    pins=N.read(N.HERE/'execution_pins.json');N.verify(pins['binding_sha256'],pins['authorization_sha256'],variant)
    folder=N.HERE/variant;l=N.Ledger.load(folder/'ledger.json',pins['binding_sha256'],pins['authorization_sha256'],variant)
    exit_evidence=N.confirm_stopped(folder)
    if l.state['status'] not in ('complete','stopped','failed') or l.state['active'] is not None:raise ValueError('Confirmed terminal ledger required')
    u,s,proof=load();finished=[];failed=[];raws=[];sources={}
    keep=lambda p:sources.update({p.relative_to(N.ROOT).as_posix():N.digest(p)})
    scale=np.asarray(N.config(variant)['action']['scale']);ix=[0,1,3,4]
    for attempt in l.state['attempts']:
        index=attempt['index'];key=('restore_' if index==4 else '')+N.identities()[index]['name'];ep=collector_output(folder,index)/key
        if attempt['status']=='failed':
            files={p.name:N.digest(p) for p in ep.rglob('*') if p.is_file()} if ep.exists() else {}
            failed.append(dict(index=index,error=attempt.get('error'),archive_files=files))
            for p in ep.rglob('*'):
                if p.is_file():keep(p)
            continue
        r=attempt['result'];p=N.ROOT/r['archive_path'];receipt=N.read(p.parent/'status.json');raw=json.loads(gzip.decompress(p.read_bytes()));_audit_physics(raw);AuditedReplay(capacity=13000)._prepare(raw['transitions'])
        if N.digest(p)!=r['archive_sha256'] or receipt['archive_sha256']!=r['archive_sha256'] or raw['fault'] is not None or raw['training_admitted'] is not False or receipt['committed']!=0 or raw['qualification_sha256']!=pins['binding_sha256'] or raw['policy_sha256']!=N.ACTOR_PIN or raw['checkpoint_sha256']!=N.CHECKPOINT_PIN or raw['case']!=N.identities()[index] or raw['seed']!=N.P.scope()['seed'] or raw['optimizer_steps_start']!=2000 or raw['optimizer_steps']!=2000:raise ValueError('Frozen source/receipt identity differs')
        from deployment_rules import DeploymentRules
        stamp=DeploymentRules(N.config(variant)['action']['scale']).classify(raw)
        if raw['learning_eligibility']!=stamp or receipt['learning_eligibility']!=stamp:raise ValueError('Deployment audit stamp differs')
        metrics=episode_metrics(raw)
        if not all(_same(r[k],v) for k,v in metrics.items()) or r['physical_substeps']!=10*len(raw['transitions']) or r['actor_states']!=len(raw['transitions']):raise ValueError('Raw metrics/cost differs')
        facts=raw['guard_facts'];guard=bool(facts['contact_reasons'] or facts['motion_reasons'] or facts['invalid_reasons'])
        if guard!=r['guard_hit'] or facts['checked_substeps']!=r['physical_substeps']:raise ValueError('Guard/count differs')
        for t in raw['transitions']:
            log=t['action_log'];expected=np.zeros(6);expected[ix]=np.asarray(log['raw_action'])*scale
            if not np.allclose(expected,log['requested_residual'],atol=1e-15,rtol=0):raise ValueError('Deployment scale wiring differs')
        active=np.asarray([t['action_log']['raw_action'] for t in raw['transitions'] if t['action_active']],dtype=float).reshape(-1,4)
        finished.append(dict(**r,stop_reason=raw['final_session'].get('reason'),guard_reasons=facts['contact_reasons']+facts['motion_reasons']+facts['invalid_reasons'],
            active_request_mean=active.mean(axis=0).tolist() if len(active) else [0.]*4,active_x_negative_fraction=float((active[:,0]<0).mean()) if len(active) else 0))
        raws.append((index,raw));keep(p);keep(p.parent/'status.json')
    restore_ok=False
    if l.state['status']=='complete':
        first=next(raw for i,raw in raws if i==0);last=next(raw for i,raw in raws if i==4)
        proof_restore=N.read(folder/'restoration.json');main=N.read(folder/'main_load.json');rest=N.read(folder/'restore_load.json')
        if not equal_trace(first,last) or not N.restoration_valid(l.state['attempts'][-1]['result']) or main['pid']==rest['pid'] or proof_restore['restore_worker_pid']!=rest['pid'] or not proof_restore['exact_physical_replay']:raise ValueError('Independent actual replay differs')
        restore_ok=True
    costs=[];cost_complete=True
    for phase in ('main','restore'):
        p=folder/(phase+'_costs.json')
        if p.exists():
            cost=N.read(p)
            if cost['training_batches'] or cost['critic_forward'] or cost['physical_substeps']!=cost['substep_forwards'] or cost['module_calls']>32*cost['actor_states']:raise ValueError('Actual computation differs')
            costs.append(cost)
        elif (folder/('process' if phase=='main' else 'restore_process')/'started.json').exists():cost_complete=False
        for suffix in ('_load.json','_verification.json'):
            p=folder/(phase+suffix)
            if p.exists():
                v=N.read(p)
                if suffix=='_load.json' and (not v['updater_complete_equal'] or v['actor_sha256']!=N.ACTOR_PIN or v['new_model_calls'] or v['new_physics']):raise ValueError('Restore before physical gate differs')
                if suffix=='_verification.json' and not v['frozen_updater_unchanged']:raise ValueError('Frozen updater verification differs')
    totals={k:sum(x[k] for x in costs) for k in ('actor_states','module_calls','physical_substeps')}
    if totals['physical_substeps']>len(l.state['attempts'])*130000 or totals['actor_states']>len(l.state['attempts'])*13000:raise ValueError('Reserved budget exceeded')
    if not failed and (totals['actor_states']!=sum(x['cycles'] for x in finished) or totals['physical_substeps']!=10*sum(x['cycles'] for x in finished)):raise ValueError('Complete cost total differs')
    for p in folder.rglob('*'):
        if p.is_file() and p.name!='assessment.json':keep(p)
    stage_rows=[r for r in finished if r['index']<4]
    result=dict(variant=variant,status=l.state['status'],operational_fault=l.state['status']=='failed' or bool(failed),restore_ok=restore_ok,
        development_completed=len(stage_rows),development_success=sum(r['success'] for r in stage_rows),
        ordinary_or_guard_failures=sum(not r['success'] for r in stage_rows),rows=finished,failed_attempts=failed,
        unexecuted_indices=list(range(len(l.state['attempts']),5)),accounting=l.accounting(),actual_costs=totals,actual_costs_complete=cost_complete,
        reserved_physical_substep_upper_bound=130000*len(l.state['attempts']),worker_stop_confirmed=True,supervised_exit_sha256=exit_evidence,offline_calls=calls,
        source=proof,deploy_scale=N.config(variant)['action']['scale'],independent_test=0,b2_complete=False,
        interpretation='frozen_deployment_screen_only' if variant=='small' else 'frozen_C2000_development_evaluation',
        result_inputs_sha256=sources)
    if any(calls.values()):raise ValueError('Unexpected audit computation')
    N.write(folder/'assessment.json',result);print(json.dumps({k:result[k] for k in ('variant','status','operational_fault','restore_ok','development_completed','development_success','ordinary_or_guard_failures','actual_costs')},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--variant',choices=['base','small'],required=True);audit(p.parse_args().variant)
