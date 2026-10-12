"""Deliberately synthetic assessor inputs. Never a dynamics or task-success claim."""
from copy import deepcopy
import math
from scope_contract import ROOT,read,proposal,attempt_specs,case_kwargs
from offline_math import numerics


def fixture(*,success):
    common=read(ROOT/proposal()['parent']['configuration'])['common'];n=numerics()
    spec=attempt_specs(proposal())[9];a=math.pi/1440
    def state(t,z,quat):
        return dict(time_s=t,position_m=[0.,0.,z],quaternion_wxyz=quat,
            velocity_world=[0.]*6,contact_wrench_G=[0.]*6,contact_wrench_M=[0.]*6,penetration_m=0.,contact_count=0,
            limited_command_world=[0.]*6,phase='STOPPING',reference_qpos=[0.,0.,z,1.,0.,0.,0.])
    initial=state(0.,-.004,[math.cos(a),math.sin(a),0.,0.])
    controller=dict(phase='INSERT',phase_start=0.,search_origin=[0.]*3,search_count=0,history=[],theta=0.,
        admittance_velocity=[0.]*4,admittance_offset=[0.]*4,episode_peak_z_m=None,search_progress_origin_z_m=None,
        rotation_risk_since_s=None,search_load_since_s=None,admittance_xy_rebase_count=0,reference_release_requested=False)
    snapshot=dict(cycle_id=0,time_s=0.,state=initial,controller_state=controller,residual_enabled=False,
                  base_command=[0.]*6,policy_observation=[0.]*137,policy_raw={})
    context=dict(base=[0.]*6,action=[0.]*4,phase='INSERT',enabled=False,previous_limited=[0.]*6,dt=.002,
                 reference_xy=None,radius=.00012,next_theta=0.,search_config=common['b2_config'])
    ctx=deepcopy(context);ctx.pop('base');ctx.pop('action')
    from types import SimpleNamespace
    observations=[];builder=n['V4ObservationBuilder'](initial,SimpleNamespace(**common['b2_config']))
    def decorate(snapshot):
        context=dict(reason=None,recovery_state=None,recovery_count=0,hold_start=None,wait_start=None,
            actual_stop_start=None,previous_residual=[0.]*4,previous_filter_fraction=1.,
            guard_facts=dict(simulation_valid=True,contact_reasons=[],motion_reasons=[],invalid_reasons=[]))
        observations.append(dict(snapshot=deepcopy(snapshot),context=context))
        vector,policy_raw=builder.capture(SimpleNamespace(**snapshot),context,refresh=True)
        snapshot.update(policy_observation=vector.tolist(),policy_raw=policy_raw)
    decorate(snapshot)
    ctx['search_config']=SimpleNamespace(**ctx['search_config'])
    command,log=n['compose_continuation_command']([0.]*6,[0.]*4,**ctx)
    log['actual_end_limited_command']=[0.]*6
    rows=[];trace=[deepcopy(initial)];reward=n['EpisodeReward'](.004);outcome='FULL_SUCCESS' if success else 'TASK_FAILURE'
    for i in range(1001):
        t=(i+1)*.002;row=state(t,0. if success else -.004,[1.,0.,0.,0.])
        after=deepcopy(snapshot);after.update(cycle_id=i+1,time_s=t,state=row)
        decorate(after)
        parts=reward.advance(advance_m=row['position_m'][2]+.004,dt=.002,force_N=0.,torque_G_Nm=0.)
        parts['terminal']=reward.finalize(outcome) if i==1000 else 0.;parts['total']+=parts['terminal']
        result=dict(next_snapshot=after,trace_row=row,dt=.002,done=i==1000,executed_command=[0.]*6,
                    action_log=deepcopy(log),cycle_peaks=dict(force_N=0.,torque_G_Nm=0.,penetration_m=0.,samples=10),reward_terms=parts)
        rows.append(dict(before=deepcopy(snapshot),after=after,requested=[0.]*4,composition=[deepcopy(context)],result=result))
        snapshot=deepcopy(after);trace.append(row)
    return dict(version='b2_pose_scope_raw_v1',spec=spec,binding_sha256='fixture',fault=None,
        simulation_case=case_kwargs(spec['case']),initial=initial,trace=trace,cycles=rows,
        parameters=dict(dynamic_config=common['dynamic_config'],guard_config=common['guard_config']),
        costs=dict(case_environment_instances_attempted=1,case_environment_instances_completed=1,
            reset_attempts=1,resets_completed=1,learner_constructions=0,tensor_reads=0,network_forwards=0,
            optimizer_updates=0,replay_publications=0,native_step_calls=10010),
        wall_seconds=1.,physical_substeps=10010,control_cycles=1001,task_end_time_s=.2,audit_end_time_s=2.002,
        stop_time=.002,events=[dict(time_s=.002,phase='STOPPING',reason='SYNTHETIC_FIXTURE')],
        stop_samples=[dict(time_s=i*.0002,linear_m_s=0.,angular_rad_s=0.) for i in range(9510,10011)],
        guard_facts=dict(simulation_valid=True,invalid_reasons=[],contact_reasons=[],motion_reasons=[],
                        checked_substeps=10010,max_rotation_from_start_rad=math.pi/720),
        outcome=dict(simulation_valid=True,physical_stopped=True,task_outcome=outcome,guard_violations=dict(contact=False,motion=False)),
        final_session=dict(task_finished=True,reason='GEOMETRIC_SUCCESS' if success else 'TIMEOUT',phase='STOPPING'),
        peaks=dict(force_N=0.,torque_G_Nm=0.,penetration_m=0.,speed_m_s=0.),
        observations=observations,observation_schema=builder.schema)
