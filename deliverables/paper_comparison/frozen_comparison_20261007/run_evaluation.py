"""One-claim evaluation only; reuse frozen PC-06 physics, sources and policies."""
import argparse, gzip, hashlib, json, os, sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))
PRIOR=ROOT/'deliverables/paper_comparison/v4_learning_requalification_20261006'
PRIOR_SEAL='fd98d247484e919c3c4e099d03575b1d4d40e977a5da939efc088759c84b9ed5'
PILOT_PIN='5a6da84a149bc1e5315eb308c65a86e20375bdb0788e09a2058a27ee638cc74f'
PLAN='docs/superpowers/plans/2026-10-07-v4-frozen-comparison.md'
TEST_SEED=2026100701
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)

def holdout_cases():
    rng=np.random.default_rng(TEST_SEED);out=[]
    for i in range(4):
        r=float(np.sqrt(rng.uniform(110**2,150**2)));angle=float(rng.uniform(i*np.pi/2,(i+1)*np.pi/2))
        out.append(dict(id=f'holdout_{i+1:02d}',x_um=float(r*np.cos(angle)),y_um=float(r*np.sin(angle))))
    return out

def attempt_specs(common):
    dev=common['cases']
    if len(dev)!=5 or len({p['id'] for p in dev})!=5:raise ValueError('Five distinct development cases required')
    out=[]
    for scope,points,providers in [('development',dev,('B2','F0','S0')),
                                   ('first_use_frozen_position_test',holdout_cases(),('B2','F2000','S2000'))]:
        for i,p in enumerate(points):
            for provider in providers:
                out.append(dict(id=('dev' if scope=='development' else 'test')+'_'+provider+'_'+p['id'],provider=provider,
                    mode='S50' if provider.startswith('S') else 'F50',stage='final',case_index=i,case=p,evaluation_scope=scope))
    return out

def next_spec(ledger,specs):
    if ledger['status'] in ('error','controlled_stop','complete'):return None
    entries=ledger['episodes'];ids=[e['id'] for e in entries]
    if len(specs)!=27 or len(set(ids))!=len(ids) or ids!=[s['id'] for s in specs[:len(ids)]] or len(ids)>27:
        raise RuntimeError('Unknown/duplicate/out-of-order/excess attempt')
    if any(e['status']!='finished' for e in entries):raise RuntimeError('Unfinished attempt cannot be retried')
    return specs[len(ids)] if len(ids)<len(specs) else None

class ZeroUpdater:
    """Pure zero residual provider. No network or optimizer is constructed."""
    def __init__(self):self.counts=dict(critic=0,actor=0,temperature=0,target=0)
    def predict(self,observation,deterministic=False):return np.zeros(4,dtype=np.float32),None
    def fingerprints(self):return dict(actor=hashlib.sha256(b'pc07-pure-zero-residual-provider-v1').hexdigest())
    def _snapshot(self):return dict(counts=dict(self.counts),provider='pure_zero_residual')

def verify_evaluation(raw,spec,before,after):
    from tools.learning.sac_checkpoint import _same
    if not _same(before,after):raise ValueError('Frozen model/optimizer/RNG state changed')
    if (raw['episode_id']!=spec['id'] or raw['case']!=spec['case'] or raw['mode']!=spec['mode'] or
        raw['scope']!='frozen_development_evaluation' or raw['stage']!='final' or
        raw['optimizer_steps_start']!=raw['optimizer_steps'] or raw['optimizer_steps']!=before['counts']['critic']):
        raise ValueError('Registered case/scope/mode/update count differs')
    if spec['provider']=='B2':
        if not raw['actions'] or any(any(float(x)!=0. for x in row[k]) for row in raw['actions']
             for k in ('raw_action','requested_residual','applied_residual','effective_command_delta')):
            raise ValueError('B2 received nonzero residual')
    return dict(provider_calls=raw['policy_calls'],network_policy_calls=0 if spec['provider']=='B2' else raw['policy_calls'],
        state_unchanged=True,optimizer_updates=0,published_transitions=0)

def reconcile_calls(ledger):
    """Count actual recorded calls on both success and fault paths, once."""
    provider_total=network_total=0
    for entry in ledger['episodes']:
        calls=entry.get('policy_calls',0)
        if type(calls) is not int or calls<0:raise ValueError('Invalid actual call count')
        network=0 if entry['spec']['provider']=='B2' else calls
        entry['network_policy_calls']=network
        provider_total+=calls;network_total+=network
    ledger['policy_calls']=provider_total;ledger['network_policy_calls']=network_total

def verify_sources(config):
    from tools.validation.run_v4_learning_pilot import PilotAdmission
    from tools.evaluation.paper_comparison import comparison_key
    if sha(PRIOR/'delivery_manifest.json')!=PRIOR_SEAL:raise ValueError('PC-06 seal changed')
    a=PilotAdmission(PRIOR,PILOT_PIN);a.verify('F50');a.verify('S50')
    original=read(PRIOR/'configuration.json')
    if config['common']!=original['common'] or config['common_key']!=comparison_key(original['common']):raise ValueError('Common physics/source contract changed')
    if config['attempts']!=attempt_specs(original['common']):raise ValueError('Evaluation matrix changed')
    for n,d in config['evaluation_input_sha256'].items():
        if sha(ROOT/n)!=d:raise ValueError('Evaluation source changed: '+n)
    if sha(OUT/'model.xml')!=original['common']['canonical_model_sha256']:raise ValueError('Evaluation model changed')
    for reference in config['checkpoints'].values():
        p=PRIOR/'run/checkpoints'/reference['label']
        if sha(p/'manifest.json')!=reference['pin'] or sha(p/'state.pt')!=reference['state_sha256']:raise ValueError('Frozen checkpoint changed')
    return a

def prepare():
    from tools.validation.run_clearance_preflight import write,now
    if (OUT/'configuration.json').exists():raise FileExistsError('Evaluation already prepared')
    if sha(PRIOR/'delivery_manifest.json')!=PRIOR_SEAL:raise ValueError('Wrong PC-06 seal')
    for n,m in read(PRIOR/'delivery_manifest.json')['files'].items():
        if sha(PRIOR/n)!=m['sha256']:raise ValueError('PC-06 archive changed: '+n)
    c=read(PRIOR/'configuration.json');cp={}
    for provider,label in [('F0','F50_zero'),('S0','S50_zero'),('F2000','F50_online_3'),('S2000','S50_online_3')]:
        p=PRIOR/'run/checkpoints'/label
        cp[provider]=dict(label=label,pin=sha(p/'manifest.json'),state_sha256=read(p/'manifest.json')['state_sha256'])
    (OUT/'model.xml').write_bytes((PRIOR/'model.xml').read_bytes())
    names=[PLAN,(OUT/'run_evaluation.py').relative_to(ROOT).as_posix(),(OUT/'test_evaluation.py').relative_to(ROOT).as_posix()]
    config=dict(version='pc07_frozen_evaluation_v1',created_at=now(),authorization='继续进行下一步',
        purpose='evaluation_only',common=c['common'],common_key=c['common_key'],attempts=attempt_specs(c['common']),
        inherited_development=[dict(id=e['id'],mode=e['spec']['mode'],case=e['spec']['case'],archive_sha256=e['archive_sha256'])
            for e in read(PRIOR/'run/ledger.json')['episodes'] if e['spec']['stage']=='final'],
        evaluation_set_sha256=hashlib.sha256(canonical(holdout_cases()).encode()).hexdigest(),test_sampling_seed=TEST_SEED,
        evaluation_input_sha256={n:sha(ROOT/n) for n in names},checkpoints=cp,qualification_sha256=PILOT_PIN,
        max_new_episodes=27,prior_cumulative=173,cumulative_limit=200,formal_updates=0,published_transitions=0,
        max_cycles=14500,per_episode_wall_s=1200,scope='single_seed_development_and_four_first_use_positions',
        test_reuse_rule='These four cases are consumed after this evaluation; not unseen final tests for later tuning')
    verify_sources(config);write(OUT/'configuration.json',config);print('Prepared 27 evaluations; no physical resets/updates/publication')

def qualify():
    from tools.validation.run_clearance_preflight import write,now
    c=read(OUT/'configuration.json');verify_sources(c);v=read(OUT/'verification.json');r=read(OUT/'review.json')
    if not v['passed'] or r['critical'] or r['important']:raise ValueError('Evaluation verification/review failed')
    if v['evaluation_input_sha256']!=c['evaluation_input_sha256'] or r['evaluation_input_sha256']!=c['evaluation_input_sha256']:
        raise ValueError('Tests/review source mismatch')
    q=dict(version='pc07_frozen_evaluation_qualification_v1',created_at=now(),evaluation_admitted=True,training_admitted=False,
        max_new_episodes=27,formal_updates=0,prior_cumulative=173,cumulative_limit=200,prior_seal=PRIOR_SEAL,
        evidence_sha256={n:sha(OUT/n) for n in ('configuration.json','model.xml','verification.json','verification.txt','review.json')})
    write(OUT/'qualification.json',q);pin=sha(OUT/'qualification.json');write(OUT/'qualification_pin.json',dict(sha256=pin));print(pin)

def execute(pin):
    from tools.validation.run_clearance_preflight import write,now,archive_episode
    from tools.validation.run_v4_learning_pilot import rollout,audit_evaluation
    from tools.learning.v4_checkpoint import read_checkpoint
    if not pin or sha(OUT/'qualification.json')!=pin:raise ValueError('Out-of-band evaluation pin differs')
    q=read(OUT/'qualification.json')
    if not q['evaluation_admitted'] or q['training_admitted'] or q['formal_updates']!=0 or q['max_new_episodes']!=27:raise ValueError('Wrong evaluation qualification')
    for n,d in q['evidence_sha256'].items():
        if sha(OUT/n)!=d:raise ValueError('Evaluation evidence changed: '+n)
    config=read(OUT/'configuration.json');admission=verify_sources(config)
    run=OUT/'run';run.mkdir(exist_ok=False)
    ledger=dict(status='prepared',started_at=now(),episodes=[],max_new_episodes=27,prior_cumulative=173,cumulative_limit=200,
        formal_updates=0,published_transitions=0,policy_calls=0,network_policy_calls=0,retry_allowed=False,
        qualification_sha256=pin,first_use_test_cases=holdout_cases(),policy_loads={})
    write(run/'ledger.json',ledger);providers={}
    try:
        while True:
            if (OUT/'STOP').exists():ledger['status']='controlled_stop';break
            spec=next_spec(ledger,config['attempts'])
            if spec is None:ledger['status']='complete';break
            if sha(OUT/'qualification.json')!=pin or any(sha(OUT/n)!=d for n,d in q['evidence_sha256'].items()):raise ValueError('Pinned execution configuration/evidence changed')
            verify_sources(config);p=spec['provider'];mode=spec['mode']
            if p not in providers:
                binding=admission.verify(mode)
                if p=='B2':u=ZeroUpdater();warm=0;reference=None
                else:
                    reference=config['checkpoints'][p]
                    state,(u,pool,boundary,rngs)=read_checkpoint(PRIOR/'run/checkpoints'/reference['label'],expected_digest=reference['pin'],expected_binding=binding,admission=admission)
                    warm=state['warm']['draws'];del state,pool,boundary,rngs
                    if u.counts['critic']!=(2000 if p.endswith('2000') else 0):raise ValueError('Wrong frozen update count')
                providers[p]=SimpleNamespace(updater=u,binding=binding,warm_draws=warm)
                ledger['policy_loads'][p]=dict(checkpoint=reference,counts=dict(u.counts),fingerprints=u.fingerprints(),read_only=True)
                write(run/'ledger.json',ledger);print('Loaded frozen provider '+p,flush=True)
            chain=providers[p];before=chain.updater._snapshot()
            entry=dict(id=spec['id'],spec=spec,status='running',started_at=now());ledger['episodes'].append(entry);ledger['status']='running';write(run/'ledger.json',ledger)
            raw=rollout(OUT,chain,spec,entry,ledger,checkpoint=config['checkpoints'].get(p))
            audit_evaluation(raw);checks=verify_evaluation(raw,spec,before,chain.updater._snapshot());verify_sources(config)
            raw.update(provider=p,collector_scope=raw['scope'],scope=spec['evaluation_scope'],evaluation_scope=spec['evaluation_scope'],
                evaluation_qualification_sha256=pin,evaluation_set_sha256=config['evaluation_set_sha256'],evaluation_checks=checks,
                network_policy_calls=checks['network_policy_calls'])
            entry.update(evaluation_checks=checks,evaluation_scope=spec['evaluation_scope'],network_policy_calls=checks['network_policy_calls'])
            entry['archive_sha256']=archive_episode(run/(spec['id']+'.json.gz'),raw)
            reconcile_calls(ledger);write(run/'ledger.json',ledger)
            del raw,before
    except BaseException as exc:
        ledger.update(status='error',error=repr(exc));reconcile_calls(ledger);write(run/'ledger.json',ledger);raise
    finally:
        reconcile_calls(ledger)
        ledger.update(ended_at=now(),unused_closed=27-len(ledger['episodes']),inputs_unchanged=False)
        try:verify_sources(config);ledger['inputs_unchanged']=True
        except Exception as exc:ledger['source_end_error']=repr(exc);ledger['status']='error'
        write(run/'ledger.json',ledger)
        print(canonical({k:v for k,v in ledger.items() if k!='episodes'}),flush=True)

if __name__=='__main__':
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_pc07'))
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','qualify','execute'));parser.add_argument('--pin');args=parser.parse_args()
    if args.action=='prepare':prepare()
    elif args.action=='qualify':qualify()
    else:execute(args.pin)
