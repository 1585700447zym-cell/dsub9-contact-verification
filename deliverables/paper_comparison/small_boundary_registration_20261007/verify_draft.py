"""Read-only draft checks; no simulation, network, tensor or optimizer imports."""
from pathlib import Path
import json,math,sys,re
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(OUT))
import build_draft as b
from update_documents import DOCS

def main():
    c=b.read(OUT/'draft_contract.json');basis=b.read(OUT/'budget_basis.json');source=b.read(OUT/'source_checks.json');checks=[]
    def check(name,value):
        if not value:raise AssertionError(name)
        checks.append(name)
    check('draft has no admission or execution grant',c['status']=='DRAFT_NOT_ADMITTED' and c['training_admitted'] is False and c['execution_authorized'] is False)
    check('actual computation all zero',[v for k,v in c['actual'].items() if k!='cumulative_dynamic']==[0]*5 and c['actual']['cumulative_dynamic']==208)
    check('paused and metadata only',c['automatic_tracking']=='PAUSED' and source['metadata_only'] and source['new_checkpoint_loads']==source['new_policy_predictions']==0)
    p=c['proposals'];attempts=p['attempts'];check('21 unique planned attempts',len(attempts)==p['physical_attempts']==21 and len({a['id'] for a in attempts})==21)
    counts={stage:sum(a['stage']==stage for a in attempts) for stage in ('preflight','initial','warmup','online','final','restore')}
    check('stage quotas',counts==dict(preflight=2,initial=5,warmup=4,online=4,final=5,restore=1))
    check('2000 batches no credit outside online',sum(a['updates'] for a in attempts)==2000 and all(a['updates']==(500 if a['stage']=='online' else 0) for a in attempts))
    check('cumulative is proposal only',p['cumulative_dynamic_limit']==208+21==229)
    check('physics cap',p['max_total_control_cycles']==21*14500 and p['max_total_physical_substeps']==10*21*14500)
    network=sum(a['stage'] in ('initial','online','final','restore') for a in attempts)*14500
    check('network and random-draw caps',p['max_control_policy_call_attempts']==network==217500 and p['max_warmup_draws']==4*14500/50==1160)
    group=c['groups']['F12p5'];check('all four physical scales',group['action_scale_SI']==[12.5e-6,12.5e-6,.000125,.000125])
    check('normalized replay distinct from physical mapping',group['normalized_action_bounds']==[-1.,1.] and 'unscaled' in group['replay_action'] and 'physical_request' in group)
    check('fresh zero start excludes trained inheritance','fresh' in group['initialization'] and 'no old replay or trained weights' in group['initialization'])
    check('inheritance technical gates not falsely complete',not any(c['inheritance_gate'][k] for k in ('numeric_origin_verified_now','adapter_implemented','behavioral_equivalence_verified','admission_verified')))
    check('25 unique source paths',len(c['inherited_evaluation'])==25 and len({r['path'] for r in c['inherited_evaluation']})==25)
    check('five fixed development points',len(c['cases'])==5 and {r['case_id'] for r in c['inherited_evaluation']}=={r['id'] for r in c['cases']})
    check('no consumed test positions',all('holdout' not in r['id'] for r in c['inherited_evaluation']) and all('holdout' not in a['id'] for a in attempts))
    criteria=c['criteria'];check('old S negative gate remains',criteria['S50_vs_F50_prior_signal'] is False and criteria['no_S50_automatic_advancement'] is True)
    check('frozen primary criteria',criteria['minimum_time_improvement']==.10 and criteria['maximum_peak_force_relative_increase']==.05 and criteria['failure_penalty_s']==26.)
    check('incomplete matrix is not a victory',criteria['matrix_complete'] and criteria['all_valid_and_stopped'] and 'matrix stays missing' in c['stop']['physical_guard'])
    check('stops and no retries',c['stop']['retries'] is False and 'no start' in c['stop']['time_budget'] and 'do not collect extra warmup' in c['stop']['warmup_gate_failure'])
    recomputed=basis['F50_14_episode_wall_s']+basis['F0_five_point_wall_s']+2*basis['B2_five_point_wall_s']/5+basis['source_overhead_s']/2
    check('wall estimate independently sums recorded terms',math.isclose(recomputed,basis['proposed_21_episode_reference_s'],abs_tol=1e-9,rel_tol=0))
    check('fallback has no silent grant',basis['nonselected_full_retrain']['physical_attempts']==59 and basis['nonselected_full_retrain']['formal_batches']==6000 and 'not authorized' in basis['nonselected_full_retrain']['note'])
    check('hard limits not predicted runtime',p['whole_execution_wall_limit_s']==21600 and basis['planning_window_hours']==[2.,4.] and basis['proposed_reference_hours']<4.)
    check('total hard wall cap may leave incomplete matrix',basis['minimum_sum_of_individual_wall_caps_s']==30000>p['whole_execution_wall_limit_s'] and 'incomplete matrix' in basis['completion_not_guaranteed'])
    check('source hashes unchanged',b.sources()==source['proof'])
    for r in c['inherited_evaluation']:check('inherited SHA '+r['id'],b.sha(ROOT/r['path'])==r['sha256'])
    plan=ROOT/'docs/superpowers/plans/2026-10-07-small-boundary-fair-comparison.md'
    spec=ROOT/'docs/superpowers/specs/2026-10-07-small-boundary-fair-comparison-design.md'
    check('future plan entirely pending','- [x]' not in plan.read_text(encoding='utf8') and '- [ ]' in plan.read_text(encoding='utf8'))
    check('design declares draft not admission','training_admitted=false' in spec.read_text(encoding='utf8'))
    for p in [plan,spec,OUT/'结果说明.md']:
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',p.read_text(encoding='utf8')):
            check('local link '+p.name+' '+target,(p.parent/target.split('#')[0].strip()).resolve().exists())
    for name in DOCS:
        text=(ROOT/name).read_text(encoding='utf8');current=text.split('<!-- pc11-current -->')[1].split('<!-- /pc11-current -->')[0]
        check('current draft status '+name,all(x in current for x in ('草案完成','208','PAUSED','新训练准入无','执行未开始')))
        check('snapshot '+name,(ROOT/name).read_bytes()==(OUT/'documents_snapshot'/name).read_bytes())
    seal=OUT/'delivery_manifest.json'
    if seal.exists():
        for rel,m in b.read(seal)['files'].items():check('sealed '+rel,(OUT/rel).stat().st_size==m['bytes'] and b.sha(OUT/rel)==m['sha256'])
    result=dict(passed=True,checks=len(checks),check_names=checks,source_proof=source['proof'],
        actual_new_computation=0,cumulative_dynamic=208,draft_budget_only=dict(dynamics=21,formal_batches=2000,cumulative_limit=229),
        training_admitted=False,execution_authorized=False,automatic_tracking='PAUSED',
        scope='draft arithmetic, source metadata, status and document consistency; no implementation, numeric admission, physics or learned benefit validation')
    if not seal.exists():b.write(OUT/'verification.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='check_names'},ensure_ascii=False))

if __name__=='__main__':main()
