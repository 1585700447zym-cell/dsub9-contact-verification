from pathlib import Path
import sys,unittest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from gate_contract import verify_grant
from joint_contract import read,sha

class OldGrantTests(unittest.TestCase):
    def test_actual_closed_scope16_grant_cannot_authorize_new_candidate(self):
        old=HERE.parent/'b2_warm_reconstruction_execution_20261009'
        self.assertEqual(read(old/'authorization_closure.json')['status'],'CLOSED_ERROR')
        with self.assertRaises(ValueError):
            verify_grant(read(HERE/'candidate.json'),read(old/'grant.json'),read(old/'grant_pin.json')['sha256'],sha(HERE/'source_binding.json'))

if __name__=='__main__':unittest.main(verbosity=2)
