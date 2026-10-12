"""Draft registration from sealed metadata only; no tensor/physics imports."""
from pathlib import Path
import datetime,hashlib,json
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];BASE=ROOT/'deliverables/paper_comparison'
SEALS={
 'v4_learning_requalification_20261006':'fd98d247484e919c3c4e099d03575b1d4d40e977a5da939efc088759c84b9ed5',
 'frozen_comparison_20261007':'8c64d623247c31e217f71e90cbb473c3d21a05c49360f10872dab4eddd36596c',
 'residual_effect_diagnosis_20261007':'1500e169da44e364c33dc01e84b30538b3de2abedb37c9486055d6fe4687a76f',
 'contact_gate_probe_20261007':'c123f8f1f445c856e04222156f519e7b39e5cb8097e00bd646720f95858d3038',
 'search_path_comparison_20261007':'e40e58a4523d493416068c1a5326377ebd58a1e5390aff289c0b83f478769736'}
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def sources():
    counts={}
    for name,pin in SEALS.items():
        folder=BASE/name;assert sha(folder/'delivery_manifest.json')==pin,name
        files=read(folder/'delivery_manifest.json')['files'];counts[name]=len(files)
        for rel,m in files.items():assert (folder/rel).stat().st_size==m['bytes'] and sha(folder/rel)==m['sha256'],rel
    inputs=read(BASE/'v4_learning_requalification_20261006/configuration.json')['input_sha256']
    for rel,pin in inputs.items():assert sha(ROOT/rel)==pin,rel
    return dict(sealed_files=counts,production_inputs_unchanged=len(inputs))

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed draft')
    proof=sources();pc6=BASE/'v4_learning_requalification_20261006';pc7=BASE/'frozen_comparison_20261007'
    c6=read(pc6/'configuration.json');l6=read(pc6/'run/ledger.json');c7=read(pc7/'configuration.json');l7=read(pc7/'run/ledger.json')
    f,s=c6['methods']['F50'],c6['methods']['S50'];assert c6['common_key']==c7['common_key']
    assert {k:v for k,v in f.items() if k!='mode'}=={k:v for k,v in s.items() if k!='mode'}
    assert l6['status']==l7['status']=='complete' and l6['per_branch_updates']=={'F50':2000,'S50':2000}
    assert l7['policy_loads']['F0']['fingerprints']==l7['policy_loads']['S0']['fingerprints']==l6['origin_fingerprints']
    assert all(v==0 for v in l7['policy_loads']['F0']['counts'].values())
    inherited=[]
    for group in ('B2','F0','S0'):
        for e in l7['episodes']:
            if e['id'].startswith('dev_'+group+'_'):
                inherited.append(dict(group=group,id=e['id'],path=(pc7/'run'/(e['id']+'.json.gz')).relative_to(ROOT).as_posix(),
                    sha256=e['archive_sha256'],case_id=e['spec']['case']['id'],role='historical_development_evaluation_only'))
    for r in c7['inherited_development']:
        inherited.append(dict(group=r['mode']+'_2000',id=r['id'],path=(pc6/'run'/(r['id']+'.json.gz')).relative_to(ROOT).as_posix(),
            sha256=r['archive_sha256'],case_id=r['case']['id'],role='historical_development_evaluation_only'))
    assert len(inherited)==25
    for r in inherited:assert sha(ROOT/r['path'])==r['sha256']
    points=c6['common']['cases'];assert len(points)==5 and points[-1]['id']=='aligned'
    attempts=[dict(id='preflight_zero_y_neg',stage='preflight',case=points[0],policy='zero',updates=0),
              dict(id='preflight_bounded_axes_y_neg',stage='preflight',case=points[0],policy='registered_four_axis_script',updates=0)]
    for stage,subset in [('initial',points),('warmup',points[:4]),('online',points[:4]),('final',points),('restore',points[:1])]:
        for i,case in enumerate(subset):attempts.append(dict(id=stage+'_F12p5_'+case['id'],stage=stage,case=case,
            policy='random_hold_50_cycles' if stage=='warmup' else 'stochastic' if stage=='online' else 'deterministic',
            updates=500 if stage=='online' else 0))
    assert len(attempts)==21 and sum(x['updates'] for x in attempts)==2000
    physical=sum(e['wall_seconds'] for e in l6['episodes']);cycles=sum(e['control_cycles'] for e in l6['episodes'])
    total=(datetime.datetime.fromisoformat(l6['ended_at'])-datetime.datetime.fromisoformat(l6['started_at'])).total_seconds()
    f14=sum(e['wall_seconds'] for e in l6['episodes'] if e['spec']['mode']=='F50')
    f0=sum(e['wall_seconds'] for e in l7['episodes'] if e['id'].startswith('dev_F0_'))
    b2=sum(e['wall_seconds'] for e in l7['episodes'] if e['id'].startswith('dev_B2_'))
    estimate=f14+f0+2*b2/5+(total-physical)/2
    basis=dict(source_episode_wall_s=physical,source_whole_wall_s=total,source_overhead_s=total-physical,
        source_control_cycles=cycles,source_wall_s_per_cycle=physical/cycles,F50_14_episode_wall_s=f14,
        F0_five_point_wall_s=f0,B2_five_point_wall_s=b2,
        proposed_21_episode_reference_s=estimate,proposed_reference_hours=estimate/3600,
        formula='F50 14 episodes + F0 five points + 2*(B2 five-point wall)/5 + PC06 non-episode overhead/2',
        planning_window_hours=[2.,4.],global_execution_wall_limit_s=21600,
        minimum_sum_of_individual_wall_caps_s=21*1200+4*1200,
        completion_not_guaranteed='21 episode caps plus 4 update-block caps already sum to 30000s, reads additionally consume time; 21600s global cap may leave an incomplete matrix, no method-effect conclusion',
        interpretation='engineering extrapolation, not measured F12.5 runtime or confidence interval; excludes implementation and future multiseed/final tests',
        nonselected_full_retrain=dict(physical_attempts=59,formal_batches=6000,extra_over_selected=dict(physical_attempts=38,formal_batches=4000),
            note='three fresh learning groups with 2 common preflights plus 3*(5 initial+4 warmup+4 online+5 final+1 restore); not authorized fallback'))
    contract=dict(version='pc11_small_boundary_registration_draft_v1',status='DRAFT_NOT_ADMITTED',
        authorization_scope='registration draft only',training_admitted=False,execution_authorized=False,automatic_tracking='PAUSED',
        actual=dict(new_dynamics=0,new_physical_substeps=0,new_network_predictions=0,new_optimizer_batches=0,new_published_transitions=0,cumulative_dynamic=208),
        question='Can matched small-boundary F learning retain offset correction while reducing aligned disturbance and improve over B2 and its own zero-update policy?',
        common_source='deliverables/paper_comparison/v4_learning_requalification_20261006/configuration.json',common_key=c6['common_key'],
        common_sha256=hashlib.sha256(json.dumps(c6['common'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
        groups=dict(B2='read-only PC07 zero residual',F50='read-only matched PC06 2000 batches',S50='read-only matched PC06 2000 batches',
            F12p5=dict(new_training=True,permission='INSERT/SEARCH with all original base guards',
                action_scale_SI=[12.5e-6,12.5e-6,.000125,.000125],normalized_action_bounds=[-1.,1.],
                replay_action='unscaled four-dimensional normalized request, zero when inactive',
                physical_request='scale12.5 multiplied by normalized action before shared compositing/limits',
                observation_width=137,learning=f['learning'],warmup=f['warmup'],online=f['online'],
                zero_origin=l6['origin_fingerprints'],initialization='fresh same-seed zero-update network; replay/optimizers reset, no old replay or trained weights')),
        cases=points,inherited_evaluation=inherited,source_seals=SEALS,
        inheritance_gate=dict(metadata_verified=True,numeric_origin_verified_now=False,adapter_implemented=False,
            behavioral_equivalence_verified=False,admission_verified=False,
            requirement='original 1057 shared inputs and common key remain unchanged; new outer profile bound separately; if incompatible stop this proposal, no silent old-row retag or full-retrain fallback'),
        proposals=dict(numeric_qualification=dict(max_synthetic_update_batches=4,max_test_state_forward_evaluations=32),
            physical_attempts=21,preflight_attempts=2,learning_and_evaluation_attempts=19,formal_batches=2000,
            prior_dynamic=208,cumulative_dynamic_limit=229,max_control_cycles_per_attempt=14500,
            max_total_control_cycles=304500,max_total_physical_substeps=3045000,
            max_control_policy_call_attempts=217500,max_warmup_draws=1160,
            per_episode_wall_limit_s=1200,checkpoint_read_wall_limit_s=300,update_block_wall_limit_s=1200,whole_execution_wall_limit_s=21600,
            attempts=attempts),
        criteria=dict(failure_penalty_s=26.,minimum_time_improvement=.10,maximum_peak_force_relative_increase=.05,
            matrix_complete=True,all_valid_and_stopped=True,success_count_not_less=True,guard_count_not_more=True,
            primary_pairs=['F12p5_final vs B2','F12p5_final vs F12p5_initial'],
            secondary_pairs=['F12p5_final vs F50','F12p5_final vs S50'],aligned_precision_required=True,strict_precision_count_not_less_than_B2=True,
            S50_vs_F50_prior_signal=False,S50_prior_time_improvement_fraction=.0039,
            no_S50_automatic_advancement=True),
        stop=dict(run_or_source_or_invalid_or_stop_failure='stop whole proposal and close unused budget',
            physical_guard='stop only new F12p5 branch after stop/archive; no further formal optimization, matrix stays missing',
            warmup_gate_failure='stop; do not collect extra warmup',ordinary_task_failure='keep and continue within fixed quota',
            time_budget='reserve worst-case atomic task limit before each task; insufficient remainder means no start and unused budget closed',
            retries=False,checkpoint_selection='final 2000-batch checkpoint only; no best-of-middle selection'),
        limitations=['single previously used training seed and five development points','XY/RP bounds shrink together, not XY-only ablation',
            'S50 vs F12p5 changes permission and bounds together, not a single-variable stage-permission test',
            'S50 vs F50 prior continue gate already failed; adding a baseline cannot undo it',
            'four previously consumed first-use points are excluded from this draft','full B.2/C and paper multiseed/independent tests remain separate'])
    write(OUT/'draft_contract.json',contract);write(OUT/'budget_basis.json',basis)
    write(OUT/'source_checks.json',dict(passed=True,proof=proof,inherited_evaluations=25,
        common_key_same=True,F_S_nonmode_settings_same=True,recorded_zero_fingerprints_same=True,
        metadata_only=True,new_checkpoint_loads=0,new_policy_predictions=0,
        declaration='metadata/source verification is not numerical admission or training authorization'))
    assert sources()==proof
    print('DRAFT only: 25 inherited evaluation archives; proposed new 21 dynamics/2000 formal batches; actual new computation 0')

if __name__=='__main__':main()
