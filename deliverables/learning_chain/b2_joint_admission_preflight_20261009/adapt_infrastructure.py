"""One-time source adaptation into the new candidate only. Does not execute it."""
from pathlib import Path
OUT=Path(__file__).resolve().parent
def replace(text,old,new):
    if old not in text:raise ValueError('Missing adaptation anchor: '+old[:100])
    return text.replace(old,new)
def main():
    if (OUT/'candidate_binding.json').exists():raise PermissionError('Do not rewrite bound implementation')
    p=OUT/'scope_contract.py';t=p.read_text(encoding='utf-8')
    t=replace(t,"out.get('guard_violations')==[]","out.get('guard_violations')=={'contact':False,'motion':False}")
    p.write_text(t,encoding='utf-8')
    p=OUT/'execution_contract.py';t=p.read_text(encoding='utf-8')
    t=replace(t,'b2_pose_scope_grant_v1','b2_joint_preflight_grant_v1')
    t=replace(t,'next_attempt, case_kwargs','next_attempt, healthy, attempt_specs, case_kwargs')
    t=replace(t,'claim=claims/pin;claim.mkdir(exist_ok=False)',"(claims/'scope.consumed').mkdir(exist_ok=False)\n    claim=claims/pin;claim.mkdir(exist_ok=False)")
    a=t.index('                complete=');b=t.index("                ledger['status']",a)
    t=t[:a]+"                complete=len(ledger['attempts'])==12 and all(healthy(e) for e in ledger['attempts'])\n"+t[b:]
    t=replace(t,"9-ledger['static_attempts']","0-ledger['static_attempts']")
    t=replace(t,"16-ledger['dynamic_attempts']","12-ledger['dynamic_attempts']")
    t=replace(t,"cumulative_before=candidate['cumulative_dynamic'],training_updates=0", "cumulative_before=candidate['cumulative_dynamic'],planned_dynamic=12,environment_creations_reserved=0,resets_reserved=0,control_cycles_reserved=0,native_steps_reserved=0,training_updates=0")
    t=replace(t,"ledger[spec['kind']+'_attempts']+=1", "ledger[spec['kind']+'_attempts']+=1\n            ledger['environment_creations_reserved']+=1;ledger['resets_reserved']+=1\n            ledger['control_cycles_reserved']+=14500;ledger['native_steps_reserved']+=145000")
    p.write_text(t,encoding='utf-8')
    p=OUT/'run_preflight.py';t=p.read_text(encoding='utf-8')
    t=replace(t,'b2_preflight_rebound_20261008','b2_joint_admission_preflight_20261009')
    t=replace(t,'b2_pose_scope_binding_v1','b2_joint_preflight_binding_v1')
    t=replace(t,"'evidence_checks')","'evidence_checks','recovery_fixture','coverage_checks')")
    t=replace(t,"9-ledger['static_attempts']","0-ledger['static_attempts']")
    t=replace(t,"16-ledger['dynamic_attempts']","12-ledger['dynamic_attempts']")
    t=replace(t,"unused_static_closed=9,unused_dynamic_closed=16","unused_static_closed=0,unused_dynamic_closed=12")
    t=replace(t,"    if kind=='static':\n        if cycles or steps or elapsed>=limits['per_static_wall_s'] or static_elapsed>=limits['static_batch_wall_s']:\n            raise TimeoutError('Static no-integration/time ceiling')\n    elif kind=='dynamic':", "    if kind=='dynamic':")
    t=replace(t,"if identity['output']!=str(folder)","if (claim/'closed.json').exists():raise PermissionError('Grant already closed')\n    if identity['output']!=str(folder)")
    t=replace(t,"spec=request['spec']\n", "spec=request['spec']\n    if request['binding_sha256']!=sha(BINDING):raise ValueError('Worker binding pin mismatch')\n")
    t=replace(t,"    result=execute_matrix(candidate,folder,invoke)\n    from assess import assess\n    write(folder/'assessment.json',assess(folder))\n    write(claim/'closed.json',dict(status=result['status'],output=str(folder),unused_closed=True))\n    return result", "    try:\n        result=execute_matrix(candidate,folder,invoke)\n        from assess import assess\n        write(folder/'assessment.json',assess(folder))\n        return result\n    finally:\n        ledger=read(folder/'ledger.json') if (folder/'ledger.json').exists() else {}\n        write(claim/'closed.json',dict(status=ledger.get('status','CLOSED_ERROR'),output=str(folder),unused_closed=True,retry_allowed=False))")
    t=replace(t,"gate=ROOT/'tmp/b2_scope_supervisors'", "gate=ROOT/'tmp/b2_joint_supervisors'")
    # Reject missing/old grants in the outer CLI before starting any supervisor.
    t=replace(t,"        from deadline_guard import bounded_process\n", "        c,b=check_binding();require_interpreter(b)\n        if sha(args.grant)!=args.grant_pin:raise ValueError('Grant pin differs')\n        validate_grant(read(args.grant),sha(BINDING),c)\n        from deadline_guard import bounded_process\n")
    p.write_text(t,encoding='utf-8')
    p=OUT/'physical_worker.py';t=p.read_text(encoding='utf-8')
    t=replace(t,'case_kwargs, script_action','case_kwargs, profile_action, attempt_specs')
    t=replace(t,'b2_pose_scope_raw_v1','b2_joint_preflight_raw_v1')
    t=replace(t,"    session=ContinuationResidualSession(environment", "    from recovery_fixture import session_type\n    session=session_type(ContinuationResidualSession)(environment")
    t=replace(t,"    spec=request['spec'];folder", "    spec=request['spec']\n    if spec not in attempt_specs(proposal()):raise ValueError('Unregistered attempt')\n    folder")
    t=replace(t,"        raw['wall_seconds']=", "        raw['fixture_events']=deepcopy(session.fixture.events) if session is not None and getattr(session,'fixture',None) else []\n        raw['wall_seconds']=")
    t=replace(t,"            snap=session.reset(case,seed=20261008)", "            from recovery_fixture import RecoveryFixture\n            session.fixture=RecoveryFixture() if spec['profile']=='R_RECOVERY' else None\n            snap=session.reset(case,seed=20261009)")
    t=replace(t,"                requested=script_action(phase,elapsed,snap.residual_enabled,spec['case']['script_sign']) if spec['arm']=='script' else [0.]*4", "                requested=session.fixture.action(snap,session.recovery_state) if session.fixture else profile_action(spec['profile'],snap.cycle_id,snap.residual_enabled)")
    p.write_text(t,encoding='utf-8')
    p=OUT/'assess.py';t=p.read_text(encoding='utf-8')
    t=replace(t,'attempt_specs,script_action','attempt_specs,healthy')
    t=replace(t,'b2_pose_scope_raw_v1','b2_joint_preflight_raw_v1')
    t=replace(t,"    reward=n['EpisodeReward']", "    from coverage_checks import audit_protocol, action_coverage\n    protocol=audit_protocol(raw,spec,same)\n    reward=n['EpisodeReward']")
    t=replace(t,"        action=script_action(phase,elapsed,before['residual_enabled'],spec['case']['script_sign']) if spec['arm']=='script' else [0.]*4", "        action=protocol['expected_actions'][i]")
    t=replace(t,"        observation=observation,training_admitted=False", "        observation=observation,joint_coverage=action_coverage(raw,spec),recovery=protocol['recovery'],training_admitted=False")
    a=t.index('def information_comparison(');b=t.index('def main():',a)
    t=t[:a]+'''def assess(folder,*,verify_binding=True):
    folder=Path(folder);c=proposal();binding={'binding_sha256':None}
    if verify_binding:
        from run_preflight import check_binding,BINDING
        _,binding=check_binding();binding=dict(binding,binding_sha256=sha(BINDING))
    ledger=read(folder/'ledger.json');entries=ledger['attempts'];specs=attempt_specs(c)
    if len(entries)>12 or any(e['id']!=specs[i]['id'] or e['kind']!='dynamic' for i,e in enumerate(entries)):
        raise ValueError('Attempt ledger skipped/reordered/exceeded')
    rows=[];closed=False
    for i,spec in enumerate(specs):
        row=dict(id=spec['id'],kind='dynamic',profile=spec['profile'],case_id=spec['case']['id'],
            status='NOT_ATTEMPTED',audit_passed=False,functional_success=None)
        if i<len(entries):
            if closed:raise ValueError('Attempt occurred after closure condition')
            entry=entries[i];row['status']=entry['status']
            if entry['status']=='finished':
                path=folder/(spec['id']+'.json.gz')
                if sha(path)!=entry['archive_sha256']:raise ValueError('Raw archive SHA differs')
                row.update(assess_raw(read_archive(path),spec,binding))
                closed=not healthy(row)
            else:closed=True
        rows.append(row)
    from coverage_checks import matrix_route
    return dict(dynamic=rows,planned_dynamic=12,planned_static=0,route=matrix_route(rows),
        new_training_authorized=False,full_B2_accepted=False,independent_tests=0,retry_allowed=False,
        limitation='Fixed stress sequences and engineered recovery; no learning benefit, universal safety, or natural recovery probability claim')


'''+t[b:]
    p.write_text(t,encoding='utf-8')
    print('Adapted only the new candidate; no execution.')
if __name__=='__main__':main()
