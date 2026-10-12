"""One bounded offline protocol suite with recorded tested source fingerprints."""
import json,subprocess,sys,uuid
import paired_contract as C

def main():
    files=list(C.HERE.glob('*.py'))
    before={p.relative_to(C.ROOT).as_posix():C.digest(p) for p in files}
    tests=[str(p.relative_to(C.ROOT)) for p in C.HERE.glob('test_*.py')]
    tests+=['tests/learning/test_action.py','tests/learning/test_observation.py']
    scratch=C.ROOT/'tmp'/('stage_resume_pytest_'+uuid.uuid4().hex)
    if scratch.exists() or not scratch.resolve().is_relative_to((C.ROOT/'tmp').resolve()):raise ValueError('Fresh local pytest directory required')
    cmd=[sys.executable,'-X','utf8','-B','-m','pytest',*tests,'-q','-p','no:cacheprovider','--tb=short','--basetemp',str(scratch)]
    r=subprocess.run(cmd,cwd=C.ROOT,capture_output=True,text=True,encoding='utf-8')
    (C.HERE/'protocol_output.txt').write_text(r.stdout+r.stderr,encoding='utf-8')
    C.verify_files(before)
    C.write(C.HERE/'protocol_result.json',dict(returncode=r.returncode,all_passed=r.returncode==0,command=cmd,tested_source_sha256=before,physics_model_optimizer_calls=0,
        note='Permission and learning-state suites install explicit no-physics/no-forward/no-Adam guards; other tests are pure protocol/data tests.'))
    print((r.stdout+r.stderr)[-3500:]);return r.returncode

if __name__=='__main__':raise SystemExit(main())
