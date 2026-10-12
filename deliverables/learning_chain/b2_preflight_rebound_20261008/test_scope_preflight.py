"""Pure checks: do not import any physical/learning runtime."""
from copy import deepcopy
import importlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(OUT))
PROPOSAL = OUT / 'candidate.json'
PARENT = ROOT / 'deliverables/paper_comparison/v4_learning_requalification_20261006/configuration.json'


def temporary_directory():
    base=ROOT / 'tmp/b2_scope_pure_test_fixtures'
    base.mkdir(parents=True,exist_ok=True)
    return tempfile.TemporaryDirectory(dir=base,delete=False)


def module(name):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name != name:
            raise
        return None


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.c = json.loads(PROPOSAL.read_text(encoding='utf-8'))
        self.parent = json.loads(PARENT.read_text(encoding='utf-8'))
        self.api = module('scope_contract')
        self.assertIsNotNone(self.api, 'Missing pure scope contract implementation')

    def test_angles_reach_contact_case_once(self):
        p = self.api.case_kwargs(self.c['cases'][0])
        self.assertEqual(p, dict(name='P01', x_offset_m=0., y_offset_m=0.,
            roll_rad=math.pi/720, pitch_rad=0., start_origin_z_m=-.004, target_depth_m=.004))
        j = self.api.case_kwargs(self.c['cases'][5])
        self.assertAlmostEqual(j['x_offset_m'], -.000075, places=16)
        self.assertAlmostEqual(j['y_offset_m'], .000075, places=16)
        self.assertEqual(j['roll_rad'], -math.pi/720)
        self.assertEqual(j['pitch_rad'], math.pi/720)

    def test_malformed_and_unregistered_cases_rejected(self):
        for field, value in [('roll_deg',True),('pitch_deg',float('nan')),('roll_deg',.004363323),
                             ('x_um',76),('yaw_deg',1),('id','P99')]:
            with self.subTest(field=field, value=value):
                row = deepcopy(self.c['cases'][0]); row[field] = value
                with self.assertRaises(ValueError): self.api.case_kwargs(row)

    def test_candidate_and_parent_cannot_change(self):
        self.assertEqual(self.api.validate_candidate(self.c,self.parent), self.c)
        for field in ['cases','physical_rules','proposed_limits']:
            bad=deepcopy(self.c)
            if field=='cases':bad[field][1]=bad[field][0]
            elif field=='physical_rules':bad[field]['allow_initial_contact']=True
            else:bad[field]['dynamic_attempts']=17
            with self.assertRaises(ValueError):self.api.validate_candidate(bad,self.parent)
        bad=deepcopy(self.parent);bad['common']['guard_config']['initial_roll_pitch_limit_rad']=math.pi/120
        with self.assertRaises(ValueError):self.api.validate_candidate(self.c,bad)

    def test_pulse_exact_window_and_stop_permissions(self):
        f=self.api.script_action
        self.assertEqual(f('INSERT',.019999,True,1),[0.]*4)
        self.assertEqual(f('INSERT',.02,True,1),[.1,-.1,.1,-.1])
        self.assertEqual(f('SEARCH',.119999,True,-1),[-.1,.1,-.1,.1])
        self.assertEqual(f('SEARCH',.12,True,1),[0.]*4)
        for phase, enabled in [('STOPPING',True),('RETRACT',True),('INSERT',False)]:
            self.assertEqual(f(phase,.05,enabled,1),[0.]*4)
        for args in [('INSERT',float('nan'),True,1),('INSERT',.03,True,True)]:
            with self.assertRaises(ValueError):f(*args)

    def test_fixed_sequence_and_failure_closure(self):
        entries=[]
        first=self.api.next_attempt(entries,self.c)
        self.assertEqual((first['id'],first['kind']),('init_zero_sentinel','static'))
        for _ in range(9):
            spec=self.api.next_attempt(entries,self.c)
            entries.append(dict(id=spec['id'],kind='static',status='finished',audit_passed=True))
        self.assertEqual(self.api.next_attempt(entries,self.c)['id'],'P01_zero')
        entry=dict(id='P01_zero',kind='dynamic',status='finished',audit_passed=True,
                   outcome=dict(simulation_valid=True,physical_stopped=True,task_outcome='TASK_FAILURE'))
        entries.append(entry)
        self.assertEqual(self.api.next_attempt(entries,self.c)['id'],'P01_script')
        for change in [dict(status='running'),dict(audit_passed=False),
                       dict(outcome=dict(simulation_valid=True,physical_stopped=True,task_outcome='CONTACT_GUARD'))]:
            trial=deepcopy(entries);trial[-1].update(change)
            self.assertIsNone(self.api.next_attempt(trial,self.c))
        trial=deepcopy(entries);trial[-1]['id']='J04_script'
        with self.assertRaises(ValueError):self.api.next_attempt(trial,self.c)
        trial=deepcopy(entries[:9]);trial[0]['audit_passed']=False
        self.assertIsNone(self.api.next_attempt(trial,self.c))

    def test_full_sequence_has_no_extra_attempt(self):
        entries=[]
        for i in range(25):
            spec=self.api.next_attempt(entries,self.c)
            entry=dict(id=spec['id'],kind=spec['kind'],status='finished',audit_passed=True)
            if i>=9:entry['outcome']=dict(simulation_valid=True,physical_stopped=True,task_outcome='FULL_SUCCESS')
            entries.append(entry)
        self.assertIsNone(self.api.next_attempt(entries,self.c))
        with self.assertRaises(ValueError):self.api.next_attempt(entries+[entries[-1]],self.c)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.api=module('execution_contract')
        self.assertIsNotNone(self.api,'Missing execution gate and durable matrix')
        self.c=json.loads(PROPOSAL.read_text(encoding='utf-8'))

    def test_grant_exact_pin_limits_and_explicit_approval(self):
        g=dict(version='b2_pose_scope_grant_v1',status='OPEN',explicit_user_approval=True,
            authorization_text='synthetic unit-test fixture; no execution',binding_sha256='a'*64,
            proposal_sha256='56b1af5518ddf81573995e31585873e1a46188dba88c2fe77a1f4982ca630d0e',
            scope_key=self.c['draft_scope_key'],limits=self.c['proposed_limits'])
        self.api.validate_grant(g,'a'*64,self.c)
        for field,value in [('version','old_grant'),('status','CLOSED'),('explicit_user_approval',False),
                            ('binding_sha256','b'*64),('scope_key','c'*64),('authorization_text','')]:
            b=deepcopy(g);b[field]=value
            with self.assertRaises(ValueError):self.api.validate_grant(b,'a'*64,self.c)
        b=deepcopy(g);b['limits']['optimizer_updates']=1
        with self.assertRaises(ValueError):self.api.validate_grant(b,'a'*64,self.c)

    def test_global_claim_cannot_move_to_another_output(self):
        with temporary_directory() as t:
            base=Path(t);claims=base/'claims'
            self.api.claim_once(claims,'a'*64,base/'first',{'binding_sha256':'b'*64})
            with self.assertRaises(FileExistsError):
                self.api.claim_once(claims,'a'*64,base/'second',{'binding_sha256':'b'*64})
            self.assertFalse((base/'second').exists())

    def test_existing_output_rejected_before_claim(self):
        with temporary_directory() as t:
            p=Path(t);existing=p/'exists';existing.mkdir()
            with self.assertRaises(FileExistsError):self.api.claim_once(p/'claims','a'*64,existing,{})
            self.assertFalse((p/'claims'/('a'*64)).exists())

    def test_pose_actual_zero_or_double_conversion_rejected(self):
        case=self.c['cases'][0];a=math.pi/1440
        row=dict(position_m=[0.,0.,-.004],quaternion_wxyz=[math.cos(a),math.sin(a),0.,0.])
        self.api.check_initial_pose(case,row)
        for q in [[1.,0.,0.,0.],[math.cos(math.radians(a)),math.sin(math.radians(a)),0.,0.],[float('nan'),0,0,0]]:
            bad=deepcopy(row);bad['quaternion_wxyz']=q
            with self.assertRaises(ValueError):self.api.check_initial_pose(case,bad)

    def test_bound_files_detect_source_and_runtime_change(self):
        with temporary_directory() as t:
            p=Path(t)/'bound';p.write_text('source',encoding='utf-8')
            import hashlib
            files={str(p):hashlib.sha256(b'source').hexdigest()}
            self.api.verify_files(files)
            p.write_text('changed',encoding='utf-8')
            with self.assertRaises(ValueError):self.api.verify_files(files)

    def test_attempt_durable_before_executor_and_static_abort(self):
        with temporary_directory() as t:
            folder=Path(t);seen=[]
            def fail(spec,entry):
                ledger=json.loads((folder/'ledger.json').read_text())
                self.assertEqual(ledger['attempts'][-1]['status'],'running')
                seen.append(spec['id']);raise RuntimeError('reset failure')
            result=self.api.execute_matrix(self.c,folder,fail)
            self.assertEqual(seen,['init_zero_sentinel'])
            self.assertEqual(result['status'],'CLOSED_ERROR')
            self.assertEqual(result['dynamic_attempts'],0)
            self.assertFalse(result['retry_allowed'])

    def test_protection_closes_and_task_failure_continues(self):
        for protection,want in [(False,25),(True,10)]:
            with self.subTest(protection=protection),temporary_directory() as t:
                def fake(spec,entry):
                    row=dict(status='finished',audit_passed=True)
                    if spec['kind']=='dynamic':
                        row['outcome']=dict(simulation_valid=True,physical_stopped=True,
                            task_outcome='CONTACT_GUARD' if protection else 'TASK_FAILURE')
                    return row
                result=self.api.execute_matrix(self.c,Path(t),fake)
                self.assertEqual(len(result['attempts']),want)
                self.assertEqual(result['dynamic_attempts'],want-9)
                self.assertNotEqual(result['status'],'OPEN')

    def test_stop_before_matrix_never_invokes(self):
        with temporary_directory() as t:
            folder=Path(t);(folder/'STOP').touch()
            def forbidden(*a):self.fail('STOP still launched worker')
            result=self.api.execute_matrix(self.c,folder,forbidden)
            self.assertEqual(result['status'],'CLOSED_STOP')
            self.assertEqual(result['attempts'],[])

    def test_last_guard_or_incomplete_result_does_not_report_complete(self):
        for damage in ('guard','unfinished'):
            with self.subTest(damage=damage),temporary_directory() as t:
                def fake(spec,entry):
                    row=dict(status='finished',audit_passed=True)
                    if spec['kind']=='dynamic':
                        row['outcome']=dict(simulation_valid=True,physical_stopped=True,task_outcome='TASK_FAILURE')
                    if spec['id']=='J04_script':
                        if damage=='guard':row['outcome']['task_outcome']='CONTACT_GUARD'
                        else:row['status']='running'
                    return row
                result=self.api.execute_matrix(self.c,Path(t),fake)
                self.assertEqual(len(result['attempts']),25)
                self.assertEqual(result['status'],'CLOSED_RULE')


if __name__=='__main__':
    unittest.main(verbosity=2)
