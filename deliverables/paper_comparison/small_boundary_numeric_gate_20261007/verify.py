"""Read-only source/hash/state/snapshot/seal checks; no numeric execution."""
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from numeric_contract import ROOT,LIMITS,read,sha,digest,canonical,profile_pin,verify_runtime_files,verify_numeric_authorization
from prepare_candidate import source_proof
from update_documents import DOCS


def main():
    n=0
    def check(value,label):
        nonlocal n
        if not value:raise AssertionError(label)
        n+=1
    c=read(OUT/'numeric_candidate.json');t=read(OUT/'offline_tests.json');r=read(OUT/'review.json');p=source_proof()
    check(c['status']=='PREPARED_NOT_AUTHORIZED','state')
    for key in ['numeric_authorized','numeric_verified','training_admitted','dynamic_authorized','physical_training_admitted','physical_backend_implemented']:
        check(c[key] is False,'unearned flag '+key)
    check(c['automatic_tracking']=='PAUSED','tracking')
    check(c['profile_sha256']==profile_pin(),'profile binding')
    check(c['limits']==LIMITS and LIMITS['synthetic_update_batches']==4 and LIMITS['test_state_forward_evaluations']==32,'bounds')
    check(p==read(OUT/'source_bindings.json') and digest(p)==c['source_proof_sha256'],'source binding')
    check(p['old_files']==765 and p['shared_input_count']==1057,'old source counts')
    check(verify_runtime_files(c['runtime_file_sha256'])==36,'runtime file pins')
    check(set(c['runtime_package_paths'])=={'torch','stable_baselines3','gymnasium'},'package origins')
    for path in c['runtime_package_paths'].values():check(path in c['runtime_file_sha256'],'package init binding')
    for name,pin in c['execution_source_sha256'].items():check(sha(ROOT/name)==pin,'code changed '+name)
    for name,pin in c['hot_source_sha256'].items():check(sha(ROOT/name)==pin,'active source changed '+name)
    for name,value in c['actual_at_preparation'].items():check(value==(208 if name=='cumulative_dynamic' else 0),'unearned numeric work '+name)
    request=read(OUT/'authorization_request.json')
    check(request['explicit_user_authorized'] is False and request['status']=='REQUEST_NOT_GRANTED' and request['candidate_sha256']==digest(c),'ungranted request')
    try:verify_numeric_authorization(c,request,digest(request))
    except PermissionError:n+=1
    else:raise AssertionError('request was accepted as authorization')
    check(t['passed'] and t['exit_code']==0,'pure tests')
    for name,pin in t['source_sha256'].items():check(sha(ROOT/name)==pin,'test changed '+name)
    check(t['implementation_source_sha256']==c['execution_source_sha256'],'tests describe numeric implementation')
    for name,pin in r['validated_source_sha256'].items():check(sha(ROOT/name)==pin,'review fix validation source '+name)
    check(r['critical_open']==r['important_open']==0,'open review issue')
    for name in DOCS:
        check((ROOT/name).read_bytes()==(OUT/'document_snapshots'/name).read_bytes(),'rolling snapshot '+name)
        check('pc13-current' in (ROOT/name).read_text(encoding='utf8'),'current marker '+name)
    for phrase in ['真实数值','765','1057','208','PAUSED','4','32','未授权']:
        check(phrase in (OUT/'结果说明.md').read_text(encoding='utf8'),'report scope '+phrase)
    if (OUT/'delivery_manifest.json').exists():
        for name,m in read(OUT/'delivery_manifest.json')['files'].items():check(sha(OUT/name)==m['sha256'] and (OUT/name).stat().st_size==m['bytes'],'new seal '+name)
    print(canonical(dict(passed=True,checks=n,pure_tests=t['tests_passed'],old_files=765,shared_inputs=1057,
        actual_numeric_computations=0,cumulative_dynamic=208,status=c['status'])))
    return n


if __name__=='__main__':main()
