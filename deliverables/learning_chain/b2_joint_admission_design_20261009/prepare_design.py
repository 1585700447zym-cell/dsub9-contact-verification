"""Write a reviewable, non-executable proposal; never issue an execution grant."""
import itertools
import json
from pathlib import Path
import sys

OUT=Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation\deliverables\learning_chain\b2_joint_admission_design_20261009')
sys.path.insert(0,str(OUT))
from review_evidence import ROOT,PARENT,RAW,PC06,PC09,read,save,sha

def main():
    assert not (OUT/'delivery_manifest.json').exists()
    evidence=read(OUT/'evidence_review.json')
    cases=[e['case'] for e in read(PARENT/'analysis.json')['episodes'] if e['id'].endswith('_zero')]
    for c in cases:c.pop('script_sign',None)
    axis=[]
    for i in range(4):
        for sign in [1,-1]:
            v=[0]*4;v[i]=sign;axis.append(v)
    corners=list(map(list,itertools.product([-1,1],repeat=4)))
    profiles=[dict(id='A_AXIS',patterns=axis,blocks=[dict(hold_cycles=50,repeats=1),dict(hold_cycles=1,repeats=1)],
                   block_cycles=408),
              dict(id='B_CORNERS',patterns=corners,blocks=[dict(hold_cycles=50,repeats=1),dict(hold_cycles=1,repeats=1)],
                   block_cycles=816)]
    attempts=[dict(id=c['id']+'_'+profile['id'],kind='action_scope',case=c['id'],profile=profile['id'])
              for profile in profiles for c in cases]
    attempts += [dict(id=c['id']+'_R_RECOVERY',kind='engineered_recovery',case=c['id'],profile='R_RECOVERY') for c in cases]
    wall=sum(e['existing_wall_seconds'] for e in evidence['episodes'])
    cost=dict(existing_joint_archives=8,existing_cycles=42656,recorded_worker_wall_seconds=wall,
              observed_worker_seconds_per_cycle=wall/42656,mean_episode_extrapolation_for_12_s=wall/8*12,
              max_cycle_extrapolation_for_174000_s=wall/42656*174000,
              planning_wall_hours=[1,4],proposed_whole_wall_limit_s=21600,
              proposed_per_attempt_wall_limit_s=1200,
              limitation='Historical wall_seconds scaling only; different actions/recovery may change cost. No new benchmark. Whole limit includes audit and closure; process termination is not proof of physical stop.')
    proposal=dict(stage_id='B2-SCOPE-08',version='b2_joint_admission_design_v1',status='DESIGNED_NOT_IMPLEMENTED_NOT_AUTHORIZED',
      purpose='joint_pose_action_scope_and_engineered_recovery_preflight',
      runner_implemented=False,static_authorized=False,dynamic_authorized=False,training_admitted=False,
      actual_new_dynamic=0,actual_new_updates=0,current_cumulative_dynamic=225,
      proposed_max_new_dynamic=12,proposed_cumulative_ceiling_if_separately_approved=237,
      proposed_separate_static_attempts=0,proposed_environment_creations=12,proposed_resets=12,
      proposed_max_cycles_per_attempt=14500,proposed_max_native_steps_per_attempt=145000,
      proposed_max_cycles_total=174000,proposed_max_native_steps_total=1740000,
      proposed_training_updates=0,proposed_network_forwards=0,proposed_replay_publications=0,
      proposed_learner_constructions=0,proposed_tensor_reads=0,
      common_key=read(PC06/'configuration.json')['common_key'],
      model_sha256=sha(PC06/'model.xml'),
      action=dict(mode='F50',width=4,normalized_bounds=[-1,1],physical_scale=[50e-6,50e-6,.0005,.0005],
                  original_permission='INSERT or SEARCH AND physical RUNNING AND no pending end or guard',
                  sampling='global control-cycle index; mask rechecked every cycle; no phase-clock reset or pause of index',
                  pattern_repetition='each profile repeats 100ms hold block then 2ms hold block until normal end',
                  case_labels_used_for_action=False,profiles=profiles),
      observations=dict(width=137,version='residual_reference_whitelist_v4',normalization_changed=False,
                        clipping_review=evidence['semantic_decision'],privileged_case_features_added=False),
      cases=cases,attempts=attempts,
      engineered_recovery=dict(trigger='first prepared SEARCH with search_count==1, contact_count>0, phase_elapsed>=0.020s, original permission true, no pending or latched reason',
          fallback_if_not_reached='finish original episode; mark INSUFFICIENT_RECOVERY_COVERAGE; do not inject later or retry',
          one_shot_injection='discard only prepared SEARCH command; call existing controller transition WAIT_RECOVERY/SEARCH_EXHAUSTED at unchanged sensor state; issue existing B2_SEARCH_EXHAUSTED stop and WAIT_STOP without another controller update',
          physics_state_overwritten=False,controller_or_guard_thresholds_changed=False,original_recovery_count_limit=1,
          before_trigger_request=[0,0,0,0],masked_interval_request=[1,-1,1,-1],
          after_resume='one control cycle [0.1,-0.1,0.1,-0.1], then zero until original outcome and stop audit',
          require_measured_actual_retraction_m=.0002,require_second_search=True,
          natural_task_success_claim=False,learning_data_eligible=False,
          implementation_requires='local test fixture + offline injected-state lifecycle checks before any physical execution; not added as a production policy path'),
      coverage=dict(per_joint_case_across_A_B='each of four axes has both effective command signs while contact is present; log actual request/effect counts separately',
          force_peak='each A/B maximum-force control interval has original permission and nonzero effective residual; no shifting trigger after seeing new data',
          timing='each A/B records contact-time nonzero effect in both 50-cycle and 1-cycle hold blocks',
          torque_and_penetration='record peak intervals and nonzero overlap separately; absent overlap cannot be called covered',
          recovery='R succeeds at real retraction/resume, nonzero requests masked throughout recovery, first resumed cycle enabled, final physical stop valid',
          formal_universal_action_domain_qualification=False,statistical_success_rate_claim=False),
      stop_rules=dict(immediate_batch_stop=['source or runtime mismatch','invalid simulation','incomplete audit or not physically stopped','runtime/worker/outer timeout','any hard contact or motion guard violation'],
          normal_task_failure='retain and finish assigned matrix if integration healthy; final route REVIEW_TASK_FAILURE_NO_TRAINING',
          missing_coverage='retain fixed denominator and close; no extra attempts or adaptive amplitude/order change',
          all_checks_pass='eligible to prepare separately registered limited ordinary-SAC pilot; no automatic training or old-budget revival',
          retry_allowed=False,partial_archives_retained=True,unused_allowance_closed=True),
      cost=cost,
      scope=dict(initial_pose='four discrete J points at ±75um / ±0.25deg',P_cases='inherit no-contact functional controls; no additional P attempts',
                 original_pose_target_deg=1.5,original_target_accepted=False,continuous_scope=False,full_B2_accepted=False,C_accepted=False,
                 independent_tests=0,old_budgets_reopened=False,automatic_tracking='PAUSED'))
    save('admission_proposal.json',proposal);save('cost_basis.json',cost)
    inheritance=[
      dict(id='I1',requirement='common controller/source/model/guards',disposition='inherit exact pinned current sources and model; new worker binding still required',evidence='SCOPE-05 source binding + SCOPE-06/07 seals'),
      dict(id='I2',requirement='joint initialization and zero functional baseline',disposition='inherit J01-J04 zero/script archive checks; check initial state on each new reset, no separate duplicate static batch',evidence='SCOPE-06 static9/dynamic16'),
      dict(id='I3',requirement='stall timer saturation semantics',disposition='closed for current controller branch interpretation; no observation change required by this finding',evidence='8 SEARCH histories frozen, 8 return histories cleared, active INSERT <=0.402s; not a full Markov proof'),
      dict(id='I4',requirement='normal physical recovery lifecycle',disposition='inherit same-common-source natural zero-tilt recovery as mechanism evidence only',evidence='PC-09 G50: actual boundary displacement 254.143um, 297 masked cycles, initial tilt0, nonzero masked requests0'),
      dict(id='I5',requirement='recovery rejects/timeout/guard/masking',disposition='current PC-06 22 recorded related tests and historical B1 9 tests retained separately; new F50 fixture must pass targeted offline integration checks',evidence='historical XML entries; older B1 is not automatic current or joint physical qualification'),
      dict(id='I6',requirement='full-scale and time-varying joint action response',disposition='missing: proposed A/B 8 attempts',evidence='old script .1 amplitude, 50 contact cycles each; all peak-cycle actions zero'),
      dict(id='I7',requirement='joint real retraction and nonzero-request masking',disposition='missing: proposed R 4 engineered attempts',evidence='old joint recovery0; engineering trigger does not estimate natural recovery probability'),
      dict(id='I8',requirement='learning and independent evaluation',disposition='not included; only after preparation, fresh authorization and admission',evidence='ordinary SAC joint-pose matching, freeze/evaluate still outstanding')]
    save('inheritance_matrix.json',inheritance)
    bindings={str((ROOT/n).relative_to(ROOT)):pin for n,pin in evidence['source_sha256'].items()}
    for p in [PC06/'configuration.json',PC06/'verification.xml',PC09/'run/probe_G50_y_neg_150.json.gz',
              ROOT/'deliverables/residual_interface/b1_closeout_20260926/learning_tests.xml',PARENT/'delivery_manifest.json',
              RAW/'delivery_manifest.json',ROOT/'docs/stage_b/工程范围与姿态参数冻结记录_v1.md']:
        bindings[p.relative_to(ROOT).as_posix()]=sha(p)
    save('review_source_bindings.json',bindings)
    print('Prepared proposal: 8 action + 4 recovery = 12 maximum, not implemented or authorized.')

if __name__=='__main__':main()
