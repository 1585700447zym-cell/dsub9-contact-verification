"""Owned numeric worker. Admission and source verification precede scientific imports."""
from pathlib import Path
import argparse,importlib.abc,importlib.util,importlib.metadata,sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(OUT))
from gate_contract import Gate,verify_sources,verify_reply,READER_WALL_S
from joint_contract import read,write
from supervised import enter_gate,bounded_process

class NoPhysics(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname=='mujoco' or fullname.startswith(('mujoco.','tools.dynamics.','tools.learning.environment','tools.learning.guarded_environment')):
            raise PermissionError('Physical backend forbidden in restore gate')

def prepare_runtime(binding):
    if not sys.flags.isolated or Path(sys.executable).resolve()!=Path(binding['executable']).resolve():raise PermissionError('Pinned isolated CPU interpreter required')
    for name,path in binding['runtime_package_paths'].items():
        found=importlib.util.find_spec(name)
        if found is None or Path(found.origin).resolve()!=Path(path).resolve():raise ValueError('Wrong runtime package '+name)
    for name,version in binding['runtime']['versions'].items():
        if importlib.metadata.version(name)!=version:raise ValueError('Runtime version drift '+name)
    if 'mujoco' in sys.modules:raise PermissionError('Physics was imported before gate')
    sys.meta_path.insert(0,NoPhysics())

def main():
    p=argparse.ArgumentParser();p.add_argument('role',choices=['parent','reader']);p.add_argument('folder');p.add_argument('gate');p.add_argument('parent_pid');p.add_argument('registered');a=p.parse_args()
    enter_gate(a.gate,a.parent_pid,a.registered)
    gate=Gate(Path(a.folder).resolve(),a.role);gate.counter.claim(a.role);verify_sources(gate.binding);gate.verify();prepare_runtime(gate.binding)
    from numeric_state import NumericState,state_digest,require_equal
    numeric=NumericState(gate)
    if a.role=='parent':
        zero=numeric.load_zero();numeric.deterministic_probe();rebuilt=numeric.reconstruct(zero)
        pin=numeric.save(rebuilt);expected=state_digest(rebuilt)
        write(gate.folder/'reader_request.json',dict(manifest_sha256=pin,state_digest=expected))
        bounded_process([gate.binding['executable'],'-I','-X','utf8','-B',str(OUT/'gate_worker.py'),'reader',str(gate.folder)],
            gate.folder/'reader',READER_WALL_S)
        reply=read(gate.folder/'reader_reply.json');verify_reply(expected,reply);gate.verify();verify_sources(gate.binding)
        write(gate.folder/'assessment.json',dict(verified=True,numeric_restore_verified=True,state_digest=expected,
            replay_rows=19300,warm_draws=388,training_admitted=False,physical_resume_verified=False,cumulative_dynamic=245))
    else:
        request=read(gate.folder/'reader_request.json');loaded=numeric.load_rebuilt(request['manifest_sha256'])
        expected=numeric.reconstruct(numeric.expected_zero())
        require_equal(loaded,expected,'Independent complete reconstruction')
        numeric.restore_readback(loaded);numeric.deterministic_probe()
        if state_digest(loaded)!=request['state_digest']:raise ValueError('Parent/reader complete state differs')
        gate.verify();write(gate.folder/'reader_reply.json',dict(verified=True,live_restore_verified=True,state_digest=state_digest(loaded)))

if __name__=='__main__':main()
