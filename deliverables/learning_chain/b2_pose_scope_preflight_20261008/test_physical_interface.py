"""Fake-environment tests for the exact backend interface; zero real resets."""
from dataclasses import make_dataclass
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from test_scope_preflight import module, temporary_directory


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.api=module('physical_worker')
        self.assertIsNotNone(self.api,'Missing archive-producing backend')
        from scope_contract import proposal,attempt_specs
        self.spec=attempt_specs(proposal())[1]

    def test_static_uses_registered_angle_and_never_steps(self):
        with temporary_directory() as t:
            seen=[]
            def factory(kw,kind,common,costs):
                seen.append(kw)
                a=kw['roll_rad']/2
                row=dict(position_m=[0,0,-.004],quaternion_wxyz=[math.cos(a),math.sin(a),0,0],
                         penetration_m=0.,contact_count=0)
                def reset(case,**kwargs):
                    self.assertIs(kwargs['allow_initial_contact'],False);return row
                env=SimpleNamespace(reset=reset,observe=lambda:row,phase='RUNNING',physical_steps=0,
                    data=SimpleNamespace(time=0.),guard_facts=dict(simulation_valid=True,invalid_reasons=[],contact_reasons=[],motion_reasons=[]),
                    events=[],stop_samples=[],peaks={})
                return env,None,kw,dict(dynamic_config=common['dynamic_config'],guard_config=common['guard_config'])
            raw=self.api.run_case(dict(spec=self.spec,output=t,deadline=10**12,binding_sha256='x'),{},factory=factory)
            self.assertEqual(seen[0]['roll_rad'],math.pi/720)
            self.assertEqual(raw['physical_substeps'],0)
            self.assertEqual(raw['costs']['reset_attempts'],1)
            self.assertIsNone(raw['fault'])

    def test_reset_failure_retains_attempt_and_error_archive(self):
        with temporary_directory() as t:
            def factory(*args):
                def bad(*args,**kwargs):raise ValueError('invalid contact')
                env=SimpleNamespace(reset=bad,physical_steps=0,events=[],stop_samples=[],peaks={},guard_facts={})
                return env,None,{},{}
            with self.assertRaises(ValueError):
                self.api.run_case(dict(spec=self.spec,output=t,deadline=10**12,binding_sha256='x'),{},factory=factory)
            from assess import read_archive
            raw=read_archive(Path(t)/(self.spec['id']+'.error.json.gz'))
            self.assertEqual(raw['costs']['reset_attempts'],1)
            self.assertIsNotNone(raw['fault'])


if __name__=='__main__':unittest.main(verbosity=2)
