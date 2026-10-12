"""Generate local continuation adapters from sealed code, preserving originals."""
import ast, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap import read, write, sha
OUT = Path(__file__).resolve().parent
OLD = OUT.parent / 'b2_joint_sac_preparation_20261009'
FIX = OUT.parent / 'b2_warm_import_repair_20261009'

def one(text, old, new):
    if text.count(old) != 1: raise ValueError('Nonunique baseline fragment: ' + old)
    return text.replace(old, new, 1)

if __name__ == '__main__':
    if (OUT / 'adapter_provenance.json').exists(): raise FileExistsError('Do not rebuild prepared sources')
    provenance = {}
    for name in ('bounded_io.py', 'phase_deadline.py', 'supervised.py', 'windows_job.py'):
        shutil.copyfile(FIX / name, OUT / name); provenance[name] = dict(source=str(FIX / name), before=sha(FIX / name), after=sha(OUT / name))
    text = (FIX / 'joint_contract.py').read_text(encoding='utf8')
    start = text.index('LIMITS='); end = text.index('\n\n', start)
    text = text[:start] + "LIMITS=dict(dynamic_episodes=9,environment_creations=9,resets=9,control_cycles=130500,\n    native_steps=1305000,observations=130509,formal_updates=2000,policy_calls=130500,\n    learner_constructions=8,tensor_loads=3,checkpoint_saves=2,replay_publications=4,archive_rebuilds=28,\n    per_episode_cycles=14500,per_episode_wall_s=1200,whole_wall_s=21600,reader_wall_s=1800)" + text[end:]
    text = one(text, "for stage in ('zero','warmup','online','final','restore')", "for stage in ('online','final','restore')")
    (OUT / 'joint_contract.py').write_text(text, encoding='utf8')
    provenance['joint_contract.py'] = dict(source=str(FIX / 'joint_contract.py'), before=sha(FIX / 'joint_contract.py'), after=sha(OUT / 'joint_contract.py'))
    for name in ('joint_runtime.py', 'joint_rollout.py'):
        shutil.copyfile(OLD / name, OUT / name); provenance[name] = dict(source=str(OLD / name), before=sha(OLD / name), after=sha(OUT / name))
    text = (OLD / 'joint_chain.py').read_text(encoding='utf8')
    text = one(text, 'def audit_raw(raw,config,binding):', 'def _audit_raw(raw,config,binding):')
    text = one(text, 'class V4Chain:', "def audit_raw(raw,config,binding,*,archive_sha256=None):\n    from continuation_contract import archive_binding\n    return _audit_raw(raw,config,archive_binding(raw,binding,archive_sha256=archive_sha256))\n\nclass V4Chain:")
    (OUT / 'joint_chain.py').write_text(text, encoding='utf8')
    provenance['joint_chain.py'] = dict(source=str(OLD / 'joint_chain.py'), before=sha(OLD / 'joint_chain.py'), after=sha(OUT / 'joint_chain.py'))
    text = (OLD / 'joint_checkpoint.py').read_text(encoding='utf8')
    text = one(text, 'from joint_runtime import metered_load', 'from joint_runtime import metered_load,take')
    text = one(text, "raw=json.loads(gzip.decompress(data));out=audit_raw(raw,config,expected_binding)",
               "take('archive_rebuilds')\n        raw=json.loads(gzip.decompress(data));out=audit_raw(raw,config,expected_binding,archive_sha256=hashlib.sha256(data).hexdigest())")
    marker = '    c=V4Chain(state[\'config\'],output=output,binding=expected_binding,admission=admission)'
    text = one(text, marker, '    return install_state(state,components=(updater,replay,boundary,rngs),expected_binding=expected_binding,output=output,admission=admission)\n\ndef install_state(state,*,components,expected_binding,output,admission):\n    output=Path(output).resolve()\n    if output.exists():raise FileExistsError(output)\n    updater,replay,boundary,rngs=components\n' + marker)
    (OUT / 'joint_checkpoint.py').write_text(text, encoding='utf8')
    provenance['joint_checkpoint.py'] = dict(source=str(OLD / 'joint_checkpoint.py'), before=sha(OLD / 'joint_checkpoint.py'), after=sha(OUT / 'joint_checkpoint.py'))
    text = (OLD / 'pilot_worker.py').read_text(encoding='utf8')
    start = text.index('def state_digest('); end = text.index('\n\ndef prepare_runtime', start)
    text = text[:start] + '# Scientific adapter is imported by main only after owned GO and admission.\n' + text[end:]
    text = one(text, "label==\'final\'", "label==\'final\'") if False else text
    text = one(text, "    chain=V4Chain(learning_config(),output=folder/'run/chain',binding=admission.verify('F50'),admission=admission)",
               "    chain=load_warm(output=folder/'run/chain',admission=admission)\n    ledger['warm_source_restored']=True\n    ledger['inherited_sources']=read(OUT/'input_spec.json')\n    write(folder/'phase_deadline.json',dict(started=time.time(),limit_s=1800,kind='between_episodes'))")
    text = text.replace("checkpoints/zero", "checkpoints/warm").replace("launch_reader(folder,'zero',pin,state_digest(capture(chain)),ledger)", "launch_reader(folder,'warm',pin,runtime_digest(chain),ledger)")
    text = text.replace("ledger['zero_state_restore_verified']", "ledger['warm_state_restore_verified']")
    text = one(text, "ledger['warm_state_restore_verified']=True;write", "ledger['warm_state_restore_verified']=True;ledger['training_admitted']=True;write")
    text = one(text, "    chain=load_warm(output=folder/'run/chain',admission=admission)", "    write(folder/'phase_deadline.json',dict(started=time.time(),limit_s=1800,kind='between_episodes'))\n    chain=load_warm(output=folder/'run/chain',admission=admission)")
    text = text.replace("final_state=state_digest(capture(chain))", "final_state=runtime_digest(chain)")
    text = text.replace("actual=state_digest(capture(chain))", "actual=runtime_digest(chain)")
    text = one(text, "        for c in ('J01','J02','J03','J04'):", "        for c in (() if stage=='zero' else ('J01','J02','J03','J04')):")
    text = one(text, "        rows=[]\n        for c", "        from continuation_contract import baseline_rows\n        rows=baseline_rows() if stage=='zero' else []\n        for c")
    text = one(text, "        independent_tests=0,full_B2_accepted=False,C_accepted=False,restore_exact=True))", "        independent_tests=0,full_B2_accepted=False,C_accepted=False,restore_exact=True,baseline_inherited=True))")
    text = one(text, "    folder=Path(args.folder).resolve();admission=Admission(folder);admission.verify('F50')", "    folder=Path(args.folder).resolve();admission=Admission(folder);admission.verify('F50');admission.claim(args.role,args.label)")
    text = one(text, "    counter=Counter(folder/'counter.json');joint_runtime.configure(counter)", "    counter=Counter(folder/'counter.json');joint_runtime.configure(counter)\n    global runtime_digest,load_warm\n    from warm_adapter import runtime_digest,load_warm")
    for name, content in [('pilot_worker.py', text)]:
        ast.parse(content); (OUT / name).write_text(content, encoding='utf8')
        provenance[name] = dict(source=str(OLD / name), before=sha(OLD / name), after=sha(OUT / name))
    for p in OUT.glob('*.py'): ast.parse(p.read_text(encoding='utf8'))
    shutil.copyfile(OLD / 'model.xml', OUT / 'model.xml')
    write(OUT / 'adapter_provenance.json', provenance)
    print('Local continuation adapters generated; old code untouched; no numeric imports.')
