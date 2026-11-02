import json
from pathlib import Path
import tempfile
import unittest
from tools.learning.paired_entropy_trial import arm_configs, schedule, summarize_run
from tools.learning.five_axis_contract import learning_config


class PairedEntropyTests(unittest.TestCase):
    def test_only_entropy_differs_and_total_budget_is_bounded(self):
        source=learning_config();configs=arm_configs(source)
        self.assertEqual(source['learning']['replay_capacity'],116000)
        self.assertEqual(configs['A0']['learning']['entropy_initial'],.01)
        self.assertEqual(configs['A2']['learning']['entropy_initial'],.001)
        self.assertEqual(configs['A0']['learning']['replay_capacity'],172000)
        self.assertEqual(configs['A2']['learning']['replay_capacity'],172000)
        left=configs['A0']['learning'].copy();right=configs['A2']['learning'].copy()
        left.pop('entropy_initial');right.pop('entropy_initial')
        self.assertEqual(left,right)
        plan=schedule()
        self.assertEqual(len(plan)*2,24)
        self.assertEqual(sum(x['updates_after'] for x in plan)*2,8000)
        self.assertEqual([x['publish'] for x in plan],[True]*8+[False]*4)
        self.assertEqual([x['case']['name'] for x in plan[:4]],
                         ['YAW_P10','YAW_M10','YAW_P15','YAW_M15'])
        self.assertEqual([x['case'] for x in plan[:4]],[x['case'] for x in plan[4:8]])

    def test_partial_progress_is_counted_after_batch_interruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for arm,receipt,progress,result in [
                ('A0',dict(status='finished',reset_attempted=1,physical_substeps=3000,
                           control_cycles=300,policy_calls=200),{},
                 dict(status='FINISHED',actual_updates_for_job=500,attempted_updates_for_job=500)),
                ('A2',dict(status='initializing',reset_attempted=1,physical_substeps=0),
                      dict(cycles=400,physical_substeps=4000,reset_attempted=1,policy_calls=300),{})]:
                folder=root/arm/schedule()[0]['id'];folder.mkdir(parents=True)
                for name,data in [('receipt.json',receipt),('progress.json',progress),('job_result.json',result)]:
                    (folder/name).write_text(json.dumps(data),encoding='utf-8')
            result=summarize_run(root)
            self.assertEqual(result['initialization_attempts'],2)
            self.assertEqual(result['physical_substeps'],7000)
            self.assertEqual(result['training_updates'],500)
            self.assertEqual(result['policy_calls'],500)
            self.assertEqual(result['updates_by_arm'],dict(A0=500,A2=0))
            self.assertEqual(result['completed_jobs'],1)
            self.assertFalse(result['counts_exact'])


if __name__=='__main__':unittest.main()
