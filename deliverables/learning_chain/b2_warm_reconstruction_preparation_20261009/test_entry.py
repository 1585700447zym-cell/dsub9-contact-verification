"""Exercise refusal paths in real stdlib children, without importing numeric_state."""
from pathlib import Path
import subprocess,sys,unittest,uuid
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from joint_contract import read,write,digest
from gate_worker import NoPhysics

class EntryTests(unittest.TestCase):
    def test_unsigned_request_cannot_create_output_or_claim(self):
        folder=HERE/'test_work'/uuid.uuid4().hex;folder.mkdir(parents=True)
        grant=read(HERE/'authorization_request.json');write(folder/'grant.json',grant)
        out=HERE.parent/('never_created_'+uuid.uuid4().hex)
        p=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(HERE/'run_gate.py'),'--grant',str(folder/'grant.json'),
            '--grant-sha',digest(grant),'--output',str(out)],capture_output=True,text=True,encoding='utf8',timeout=10)
        self.assertNotEqual(p.returncode,0);self.assertIn('New explicit reconstruction grant required',p.stderr)
        self.assertFalse(out.exists());self.assertFalse((HERE/'future_claims').exists())
        self.assertNotIn('numeric_state',sys.modules)

    def test_worker_refuses_invalid_owner_before_scientific_runtime(self):
        folder=HERE/'test_work'/uuid.uuid4().hex;folder.mkdir(parents=True)
        p=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(HERE/'gate_worker.py'),'parent',str(folder),str(folder/'control'),'0','0'],
            capture_output=True,text=True,encoding='utf8',timeout=10)
        self.assertNotEqual(p.returncode,0);self.assertFalse((folder/'counter.json').exists())
        self.assertNotIn('ModuleNotFoundError',p.stderr)

    def test_physics_import_guard_rejects_native_and_wrapped_backends(self):
        guard=NoPhysics()
        for name in ('mujoco','mujoco.viewer','tools.dynamics.cartesian','tools.learning.environment','tools.learning.guarded_environment'):
            with self.assertRaises(PermissionError):guard.find_spec(name)
        self.assertIsNone(guard.find_spec('tools.learning.v4_sac'))

if __name__=='__main__':unittest.main(verbosity=2)
