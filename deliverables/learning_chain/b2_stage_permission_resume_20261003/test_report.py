import ast,copy,unittest
import paired_contract as C
from report_result import judgement

class Report(unittest.TestCase):
    def groups(self):return {k:[dict(success=True,force_peak_N=.02,task_stop_time_s=10.) for _ in range(4)] for k in ('B2','F','S')}
    def test_complete_success_is_not_automatically_mechanism_benefit(self):
        self.assertEqual(judgement({'status':'complete'},self.groups()),'successful_without_stage_advantage')
    def test_success_signal_requires_four_candidate_successes(self):
        g=self.groups();g['F'][0]['success']=False
        self.assertEqual(judgement({'status':'complete'},g),'promising_success_signal')
        g['S'][0]['success']=False
        self.assertEqual(judgement({'status':'complete'},g),'effect_target_not_met')
    def test_load_signal_compares_both_baselines_and_time(self):
        g=self.groups()
        for r in g['S']:r['force_peak_N']=.017
        self.assertEqual(judgement({'status':'complete'},g),'promising_load_signal')
        for r in g['S']:r['task_stop_time_s']=12.
        self.assertEqual(judgement({'status':'complete'},g),'successful_without_stage_advantage')
    def test_partial_guard_is_not_a_method_comparison(self):
        self.assertEqual(judgement({'status':'stopped'},{}),'controlled_guard_stop')
    def test_all_new_python_sources_parse(self):
        for p in C.HERE.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'),filename=str(p))

if __name__=='__main__':unittest.main()
