"""Verify closed one-shot evidence, unchanged sources, and immutable document snapshots."""
import argparse
import ast
import gzip
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT=ROOT/'deliverables/learning_chain/b2_rebound_execution_20261008'
SOURCE=ROOT/'deliverables/learning_chain/b2_preflight_rebound_20261008'
sys.path.insert(0,str(SOURCE))
from scope_contract import read,sha,canonical,proposal,attempt_specs
from execution_contract import validate_grant
from run_preflight import check_binding,BINDING
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md','AGENTS.md']
PARENTS=[
 ('b2_scope_audit_20261008','f0ece40fc2fc3ab83b99506bb13a59158dc0282fe674dbaf03b3f5b7e47e0576',19),
 ('b2_pose_scope_preflight_20261008','178bf8cab98360b75148b4a587838e1a3493a4739576e4b713ef08a30f00a693',63),
 ('b2_pose_scope_execution_20261008','dee846ade20816e11f5487c7968c0067bcd40c3b59d8e9e180f9138f505962fc',119),
 ('b2_scope_auditor_fix_20261008','745c3948b1b7f2876a8bb1b0ab9c556a9a797082c85ca55f5b5b99cd7e3deb56',42),
 ('b2_preflight_rebound_20261008','d373a6071a4967743b7d960b89bdb82cb2b366a85b49b7cdb933ecd416edc876',61)]
HISTORICAL=[
 ('v4_learning_requalification_20261006','fd98d247484e919c3c4e099d03575b1d4d40e977a5da939efc088759c84b9ed5',457),
 ('frozen_comparison_20261007','8c64d623247c31e217f71e90cbb473c3d21a05c49360f10872dab4eddd36596c',96),
 ('residual_effect_diagnosis_20261007','1500e169da44e364c33dc01e84b30538b3de2abedb37c9486055d6fe4687a76f',27),
 ('contact_gate_probe_20261007','c123f8f1f445c856e04222156f519e7b39e5cb8097e00bd646720f95858d3038',78),
 ('search_path_comparison_20261007','e40e58a4523d493416068c1a5326377ebd58a1e5390aff289c0b83f478769736',46),
 ('small_boundary_registration_20261007','685f844ed027ebe7a00d243f1195d41b16772d42cc45d47b92ba93b1c06473ae',26),
 ('small_boundary_execution_20261007','702c5fe5138fa2621cf17b4cb5d3c441c84b1a506f7803a8492e3691ffab3ad8',35),
 ('small_boundary_numeric_gate_20261007','51eef860885bcea78c4324149060014d8faac5ce1d8e760c0abc4a9ea68eb6e9',33),
 ('small_boundary_numeric_execution_20261008','810c95ad9eb1c393a603c7e13549d1325ac0d45914d82798e6d85e8d3f4c8312',152)]

def write_new(p,v):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--seal',action='store_true');p.add_argument('--current-docs',action='store_true');args=p.parse_args()
    if args.seal:assert not (OUT/'delivery_manifest.json').exists() and not (OUT/'verification.json').exists()
    candidate,binding=check_binding(); count=0
    def check(value,label):
        nonlocal count
        if not value:raise AssertionError(label)
        count+=1
    parent_members=0
    for name,pin,size in PARENTS:
        folder=OUT.parent/name; check(sha(folder/'delivery_manifest.json')==pin,'Parent manifest '+name)
        files=read(folder/'delivery_manifest.json')['files']; check(len(files)==size,'Parent count '+name)
        for rel,row in files.items():
            check(sha(folder/rel)==row['sha256'] and (folder/rel).stat().st_size==row['bytes'],'Parent bytes '+name+'/'+rel);parent_members+=1
    history_members=0
    for name,pin,size in HISTORICAL:
        folder=ROOT/'deliverables/paper_comparison'/name
        check(sha(folder/'delivery_manifest.json')==pin,'Historical manifest '+name)
        files=read(folder/'delivery_manifest.json')['files'];check(len(files)==size,'Historical count '+name)
        for rel,row in files.items():
            check(sha(folder/rel)==row['sha256'] and (folder/rel).stat().st_size==row['bytes'],'Historical bytes '+name+'/'+rel);history_members+=1
    check(history_members==950,'Preserved PC-06 through PC-14 members')
    check(len(binding['files'])==2173,'Complete execution input binding')
    check(sha(BINDING)=='b7746e0cfaf29317c1ae692f6ed03c685d0d1a3398965c3fa36fc012b8ed3952','Fixed runtime/source pin')
    reg=read(OUT/'registration.json'); c=read(OUT/'authorization_closure.json'); a=read(OUT/'run/assessment.json'); ledger=read(OUT/'run/ledger.json')
    grant=read(OUT/'grant.json'); validate_grant(grant,sha(BINDING),candidate)
    check(sha(OUT/'grant.json')==reg['grant_sha256']==c['grant_sha256']==sha(OUT/'run/grant.json'),'Grant exact bytes')
    check(grant['user_message']=='批准继续' and grant['explicit_user_approval'] is True,'Human approval provenance')
    check(sha(OUT/'run/ledger.json')==c['original_ledger_sha256'],'Original ledger retained')
    check(ledger['status']==c['status'] and c['status'].startswith('CLOSED_'),'Closed state retained')
    check(ledger['retry_allowed'] is False and c['old_budgets_reopened'] is False,'No retries/reopening')
    specs=attempt_specs(candidate)
    check([e['id'] for e in ledger['attempts']]==[s['id'] for s in specs[:len(ledger['attempts'])]],'Exact uninterrupted order')
    check(len(a['static'])==9 and len(a['dynamic'])==16,'Fixed denominators')
    check(ledger['unused_static_closed']==9-ledger['static_attempts'] and ledger['unused_dynamic_closed']==16-ledger['dynamic_attempts'],'All remainder closed')
    check(c['cumulative_dynamic_before']==209 and c['cumulative_dynamic_after']==209+ledger['dynamic_attempts'],'Actual cumulative attempts')
    check(len(c['consumed_claim_directories'])<=len(ledger['attempts']),'At most one physical claim per reserved attempt')
    allrows=a['static']+a['dynamic']; totals=dict(control_cycles=0,physical_substeps=0,resets_completed=0,case_environment_instances_completed=0)
    for i,e in enumerate(ledger['attempts']):
        row=allrows[i]; name=e['id']; base=OUT/'run'/name; cost=read(base.with_suffix('.costs.json'))
        supervisor=read(base.with_suffix('.supervisor.json')); check(supervisor['process_exit_confirmed'],'Worker exit '+name)
        check(all(cost[k]==0 for k in ('learner_constructions','tensor_reads','network_forwards','optimizer_updates','replay_publications')),'Zero learning '+name)
        for key in ('resets_completed','case_environment_instances_completed'):totals[key]+=cost[key]
        if e['status']=='finished':
            rawpath=base.with_suffix('.json.gz'); check(sha(rawpath)==e['archive_sha256'],'Raw identity '+name)
            with gzip.open(rawpath,'rt',encoding='utf-8') as f:raw=json.load(f)
            audit=read(base.with_suffix('.audit.json'))
            check(raw['costs']==cost and raw['fault'] is None,'Native cost completeness '+name)
            check(raw['physical_substeps']==cost['native_step_calls']==raw['guard_facts']['checked_substeps']==raw['control_cycles']*10,'Native/guard/cycle exact counts '+name)
            check(audit['archive_sha256']==sha(rawpath) and audit['binding_sha256']==sha(BINDING),'Audit receipt identity '+name)
            check(e['audit_passed'] is True and audit['assessment']==e['assessment'],'Producer audit result '+name)
            check(all(canonical(row[k])==canonical(v) for k,v in audit['assessment'].items()),'Final independent assessment equals worker '+name)
            check(e['physical_substeps_lower_bound']==e['physical_substeps_upper_bound']==raw['physical_substeps'],'Exact reserved bounds '+name)
            check(cost['resets_completed']==cost['reset_attempts']==cost['case_environment_instances_completed']==1,'One creation/reset '+name)
            check(bool(raw['runtime_proof']),'Physical runtime proof '+name)
            if e['kind']=='static':check(raw['physical_substeps']==0,'No static integration '+name)
            else:
                check(row['outcome']['physical_stopped'] is True,'Physical stop '+name)
                check(row['observation']['width']==137 and row['observation']['vectors_verified']==raw['control_cycles']+1,'Complete observations '+name)
            totals['control_cycles']+=raw['control_cycles'];totals['physical_substeps']+=raw['physical_substeps']
        else:check(row['audit_passed'] is False,'No retrospective promotion '+name)
    if c['exact_final_counts_reconciled']:
        check(totals=={k:c['actual'][k] for k in totals},'Final exact totals')
    check(c['registered_static_audit_passes']==sum(r['audit_passed'] for r in a['static']) and c['registered_dynamic_audit_passes']==sum(r['audit_passed'] for r in a['dynamic']),'Acceptance counts')
    check(c['functional_successes']==sum(r.get('functional_success') is True for r in a['dynamic']),'Functional denominator')
    check(c['strict_precision_successes']==sum(r.get('strict_precision_success') is True for r in a['dynamic']),'Precision denominator')
    check(c['original_assessment_route']==a['route']==read(OUT/'report_summary.json')['route'],'Same fixed route')
    check(not c['training_admitted'] and not c['full_B2_accepted'] and not c['C_accepted'] and c['independent_tests']==0 and c['automatic_tracking']=='PAUSED','Unqualified learning/full scope')
    for original,row in c['evidence_copies'].items():check(sha(Path(original))==sha(OUT/row['copy'])==row['sha256'],'Supervisor/claim snapshot')
    for name in DOCS:
        before=OUT/'before_documents'/name; after=OUT/'document_snapshots'/name
        check(sha(before)==reg['before_documents'][name] and after.is_file(),'Immutable before/after '+name)
        if args.current_docs:check((ROOT/name).read_bytes()==after.read_bytes(),'Latest document equality '+name)
        if name!='AGENTS.md':
            block=re.search(r'<!-- b2-scope-current -->(.*?)<!-- /b2-scope-current -->',after.read_text(encoding='utf-8'),re.S).group(1)
            check('当前阶段B.2' in block and '已完成' in block and 'B2-SCOPE-06' in block and f'实际累计动态{c["cumulative_dynamic_after"]}' in block and '完整B.2/C未验收' in block,'Correct phase/task/scope '+name)
    for name in ('结果说明.md','路线决定.md'):
        file=OUT/name
        for link in re.findall(r'\]\(([^)]+)\)',file.read_text(encoding='utf-8')):
            target=(file.parent/link.split('#')[0]).resolve()
            check(target.exists() or (args.seal and target==OUT/'verification.json'),'Report link '+link)
    for path in OUT.glob('*.py'):ast.parse(path.read_text(encoding='utf-8'));count+=1
    check(not any(k.split('.')[0] in {'numpy','mujoco','torch','stable_baselines3'} for k in sys.modules),'Verifier has no engine/numerical/learning imports')
    git=lambda *x:subprocess.check_output(['git',*x],cwd=ROOT)
    check(git('branch','--show-current').decode().strip()==reg['branch'] and git('rev-parse','HEAD').decode().strip()==reg['head'],'Original branch/HEAD')
    if args.seal:
        write_new(OUT/'verification.json',dict(status='VERIFIED_CLOSED_REBOUND_EXECUTION',stage_id='B2-SCOPE-06',assertions=count,
              bound_inputs=2173,parent_members=parent_members,historical_members=history_members,actual=c['actual'],cumulative_dynamic=c['cumulative_dynamic_after'],route=a['route'],
              full_B2_accepted=False,C_accepted=False,training_admitted=False,automatic_tracking='PAUSED'))
        (OUT/'git_status_after.txt').write_bytes(git('-c','core.quotepath=false','status','--porcelain=v1'))
        files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
        write_new(OUT/'delivery_manifest.json',dict(stage_id='B2-SCOPE-06',status='SEALED_CLOSED_EXECUTION',user_date='2026-10-08',files=files,
              cumulative_dynamic=c['cumulative_dynamic_after'],training_admitted=False,rolling_documents='immutable snapshots; roots may advance'))
    manifest=read(OUT/'delivery_manifest.json')
    for rel,row in manifest['files'].items():check(sha(OUT/rel)==row['sha256'] and (OUT/rel).stat().st_size==row['bytes'],'Sealed new member '+rel)
    print(json.dumps(dict(status='VERIFIED_CLOSED_REBOUND_EXECUTION',assertions=count,sealed_files=len(manifest['files']),manifest_sha256=sha(OUT/'delivery_manifest.json'),
                         bound_inputs=2173,parent_members=parent_members,historical_members=history_members,cumulative_dynamic=c['cumulative_dynamic_after'],route=a['route']),ensure_ascii=False))

if __name__=='__main__':main()
