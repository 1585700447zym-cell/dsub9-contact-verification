"""Prepare source-preserving joint adapters. Pure file work; never imports a backend."""
import ast
from pathlib import Path
import shutil
import subprocess
import sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from joint_contract import ROOT,COMMON,read,write,sha,digest,learning_config,training_cases,schedule,LIMITS
OLD=OUT.parent/'b2_joint_coverage_review_20261009'


def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('Expected unique source fragment: '+old)
    return text.replace(old,new,1)


def adapters():
    result={};provenance={}
    for name in ('v4_pilot_chain','v4_checkpoint'):
        source=ROOT/'tools/learning'/(name+'.py');text=source.read_text(encoding='utf-8')
        text=text.replace('from .','from tools.learning.')
        if name=='v4_pilot_chain':
            text=replace_once(text,'from tools.learning.v4_pilot_contract import canonical,validate_config,training_cases,SEED',
                'from joint_contract import canonical,validate_config,training_cases,SEED,validate_raw_identity')
            text=replace_once(text,"    out=raw['outcome'];rows=raw['transitions']","    validate_raw_identity(raw)\n    out=raw['outcome'];rows=raw['transitions']")
            dest='joint_chain.py'
        else:
            text=replace_once(text,'from tools.learning.v4_pilot_contract import canonical,sha,validate_config','from joint_contract import canonical,sha,validate_config')
            text=replace_once(text,'from tools.learning.v4_pilot_chain import V4Chain,audit_raw,streams,validate_warm','from joint_chain import V4Chain,audit_raw,streams,validate_warm')
            text=replace_once(text,'torch.load(io.BytesIO(payload),map_location=\'cpu\',weights_only=True)',"metered_load(io.BytesIO(payload),map_location='cpu',weights_only=True)")
            text=replace_once(text,'flush_write=_flush_write','from joint_runtime import metered_load\nflush_write=_flush_write')
            dest='joint_checkpoint.py'
        text=replace_once(text,'from tools.learning.v4_sac import V4Updater','from joint_runtime import V4Updater')
        ast.parse(text);result[dest]=text;provenance[dest]=dict(source=source.relative_to(ROOT).as_posix(),sha256=sha(source))
    source=ROOT/'tools/validation/run_v4_learning_pilot.py';text=source.read_text(encoding='utf-8');tree=ast.parse(text)
    parts={n.name:ast.get_source_segment(text,n) for n in tree.body if isinstance(n,ast.FunctionDef)}
    rollout=parts['rollout']
    rollout=replace_once(rollout,"case=ContactCase(point['id'],point['x_um']*1e-6,point['y_um']*1e-6,0,0,-.004,.004)","case=ContactCase(**case_kwargs(point))")
    rollout=replace_once(rollout,'    session=make_session(env,mode,common)',
        "    if asdict(env.config)!=common['dynamic_config'] or asdict(env.guard_config)!=common['guard_config']:raise ValueError('Physical configuration drift')\n    session=make_session(env,mode,common)")
    rollout=replace_once(rollout,'snap=session.reset(case,seed=SEED);trace.append(session.initial_trace_row)',
        'snap=session.reset(case,seed=SEED);check_initial_pose(point,session.initial_trace_row);trace.append(session.initial_trace_row)')
    rollout=replace_once(rollout,"deterministic=stage in ('final','restore')","deterministic=stage in ('zero','final','restore')")
    header='''"""Existing physical episode loop with explicitly preserved joint pose."""\nimport time,math\nfrom pathlib import Path\nfrom dataclasses import asdict\nfrom joint_contract import read,write,case_kwargs,check_initial_pose,SEED,canonical\nfrom tools.learning.v4_pilot_contract import permission\nfrom tools.validation.run_clearance_preflight import now,archive_episode\n\n'''
    result['joint_rollout.py']=header+parts['make_session']+'\n\n'+rollout+'\n\n'+parts['audit_evaluation']+'\n'
    provenance['joint_rollout.py']=dict(source=source.relative_to(ROOT).as_posix(),sha256=sha(source),functions=['make_session','rollout','audit_evaluation'])
    return result,provenance


def main():
    if (OUT/'registration.json').exists():raise FileExistsError('Preparation already registered')
    docs=read(OLD/'registration.json')['before_documents'];before={}
    for name in docs:
        dst=OUT/'before_documents'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst);before[name]=sha(dst)
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT).decode('utf-8')
    write(OUT/'registration.json',dict(stage_id='B2-SCOPE-12',human_request='这3处覆盖缺口不会影响训练效果或者准备吧，如果没问题就继续推进工作',
        branch=git('branch','--show-current').strip(),head=git('rev-parse','HEAD').strip(),before_documents=before,
        parent_manifest_sha256=sha(OLD/'delivery_manifest.json'),prior_dynamic=237,new_physics=0,new_learning=0))
    (OUT/'git_status_before.txt').write_text(git('status','--porcelain=v1'),encoding='utf-8')
    files,provenance=adapters()
    for name,text in files.items():(OUT/name).write_text(text,encoding='utf-8')
    write(OUT/'adapter_provenance.json',provenance)
    parent=read(COMMON/'configuration.json')
    joint_key=digest(dict(parent_common_key=parent['common_key'],cases=training_cases()))
    write(OUT/'configuration.json',dict(common=parent['common'],parent_common_key=parent['common_key'],common_key=joint_key,
        methods={'F50':learning_config()},attempts=schedule(),cases=training_cases()))
    shutil.copyfile(COMMON/'model.xml',OUT/'model.xml')
    write(OUT/'candidate.json',dict(version='b2_joint_sac_candidate_v1',status='PREPARED_NOT_AUTHORIZED',training_admitted=False,
        cumulative_before=237,cumulative_ceiling=254,limits=LIMITS,case_scope='four_fixed_discrete_development_points',
        schedule=schedule(),learning_config_sha256=digest(learning_config()),configuration_sha256=sha(OUT/'configuration.json'),
        primary_metric=dict(name='four_case_mean_failure_penalized_task_time',failure_penalty_s=26,
            comparison='F2000 versus matched F0',development_continue_relative_improvement=.10,
            additional_conditions='F2000 4/4 success; valid/stopped; no hard guards; exact independent restore',
            independent_test=False),old_weights_inherited=False,automatic_tracking='PAUSED'))
    print('Prepared three local adapters and four-point registration; no runtime imported.')


if __name__=='__main__':main()
