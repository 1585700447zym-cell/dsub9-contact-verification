"""Run only pure PC13 and sealed PC12 protocols, never actual numeric workers."""
from pathlib import Path
import json,re,subprocess,sys,uuid
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from numeric_contract import ROOT,PC12,sha,write


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed; use read-only verify.py')
    paths=sorted(OUT.glob('test_numeric_*.py'))+sorted(PC12.glob('test_small_bound_*.py'))
    implementation={p.relative_to(ROOT).as_posix():sha(p) for p in (OUT/'numeric_contract.py',OUT/'synthetic_data.py',OUT/'numeric_worker.py')}
    temp=OUT/('.test_tmp_final_'+uuid.uuid4().hex)
    if temp.exists():raise FileExistsError(temp)
    cmd=[sys.executable,'-I','-m','pytest',*[str(p) for p in paths],'-q','-p','no:cacheprovider','--basetemp='+str(temp)]
    r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
    output=r.stdout+r.stderr;match=re.search(r'(\d+) passed',output)
    result=dict(passed=r.returncode==0 and match is not None,tests_passed=int(match[1]) if match else 0,
        exit_code=r.returncode,source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in paths},output=output,
        implementation_source_sha256=implementation,
        scope='pure protocol, command data, state-comparison logic and unauthorized CLI rejection only',
        actual_learner_constructions=0,actual_tensor_reads=0,actual_network_forwards=0,actual_optimizer_batches=0,
        actual_physical_episodes=0,actual_synthetic_replay_published=0,
        excludes='not full historical suite, CPU imports, actual independent numeric restoration or physics')
    result['passed']=result['passed'] and all(sha(ROOT/name)==pin for name,pin in implementation.items())
    write(OUT/'offline_tests.json',result);print('PURE RELATED CHECKS',result['tests_passed'],result['passed'])
    if not result['passed']:raise AssertionError(output)


if __name__=='__main__':main()
