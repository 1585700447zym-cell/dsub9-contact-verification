import importlib,tempfile,unittest
from pathlib import Path

class CostReport(unittest.TestCase):
    def setUp(self):
        p=Path(__file__).with_name('report_result.py')
        self.assertTrue(p.exists(),'Resume cost report not implemented')
        self.R=importlib.import_module('report_result')
    def test_inherited_physics_excluded(self):
        rows=[dict(inherited=True,physical_substeps=100),dict(inherited=False,physical_substeps=30)]
        self.assertTrue(self.R.physical_cost_complete({'main_costs.json':{'physical_substeps_attempted':30}},['main_costs.json'],[{'status':'finished'}],rows))
        with self.assertRaises(ValueError):self.R.physical_cost_complete({'main_costs.json':{'physical_substeps_attempted':130}},['main_costs.json'],[{'status':'finished'}],rows)
    def test_missing_receipt_is_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'zero_reader_F').mkdir()
            result=self.R.audit_readers(p,{'zero_readers':{},'updates':{'F':{'attempted':0},'S':{'attempted':0}}})
            self.assertFalse(result['complete'])
            self.assertIsNone(result['readers']['F']['calls'])
    def test_proof_alone_without_exit_does_not_claim_completion(self):
        with tempfile.TemporaryDirectory() as d:
            result=self.R.audit_readers(Path(d),{'zero_readers':{'F':{'calls':{'physics':0}}},'updates':{'F':{'attempted':1},'S':{'attempted':0}}})
            self.assertFalse(result['complete'])
