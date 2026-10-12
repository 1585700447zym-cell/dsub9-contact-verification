"""Only this package's pure tests and blocked CLI; not the historical suite."""
from pathlib import Path
import json,re,subprocess,sys,uuid
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from small_bound_profile import ROOT,sha
from prepare_candidate import write


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed verification; use verify.py')
    tests=sorted(OUT.glob('test_small_bound_*.py'))
    temp=OUT/('.test_tmp_final_'+uuid.uuid4().hex)
    if temp.exists():raise FileExistsError(temp)
    command=[sys.executable,'-I','-m','pytest',*[str(p) for p in tests],'-q','-p','no:cacheprovider','--basetemp='+str(temp)]
    completed=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
    stdout=completed.stdout+completed.stderr
    match=re.search(r'(\d+) passed',stdout)
    blocked=subprocess.run([sys.executable,'-I',str(OUT/'run_small_bound_pilot.py'),'--execute'],cwd=ROOT,
        capture_output=True,text=True,encoding='utf8',errors='replace')
    inspect=subprocess.run([sys.executable,'-I',str(OUT/'run_small_bound_pilot.py'),'--inspect'],cwd=ROOT,
        capture_output=True,text=True,encoding='utf8',errors='replace')
    result=dict(passed=completed.returncode==0 and match is not None and blocked.returncode!=0 and
            'PermissionError' in blocked.stderr and inspect.returncode==0,
        tests_passed=int(match[1]) if match else 0,pytest_exit=completed.returncode,
        test_source_sha256={p.name:sha(p) for p in tests},output=stdout,
        inspect_exit=inspect.returncode,inspect_output=inspect.stdout,
        unadmitted_execute_exit=blocked.returncode,unadmitted_execute_output=blocked.stderr,
        scope='pure commands/protocol and admission rejection only; no torch learner, NN forward, optimizer or dynamics',
        excludes='full historical suite and actual numeric checkpoint serialization/restore')
    write(OUT/'offline_tests.json',result)
    print('PURE TESTS',result['tests_passed'],'PASS',result['passed'],'blocked --execute exit',blocked.returncode)
    if not result['passed']:raise AssertionError(stdout+blocked.stderr)


if __name__=='__main__':main()
