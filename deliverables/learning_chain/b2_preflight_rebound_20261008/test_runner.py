"""Process and CLI tests use inert Python children; never load the physics engine."""
from pathlib import Path
import importlib
import json
import subprocess
import sys
import time
import unittest
from test_scope_preflight import temporary_directory, module, OUT, ROOT


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.api=module('run_preflight')
        self.assertIsNotNone(self.api, 'Missing fail-closed runner')

    def test_missing_grant_and_direct_worker_fail_before_runtime(self):
        for args in [['--execute'],['--worker','absent.json','--request-pin','a'*64]]:
            result=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(OUT/'run_preflight.py'),*args],
                                  capture_output=True,text=True,timeout=15)
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('mujoco',result.stdout.lower())
        self.assertFalse(any(k.split('.')[0] in ('mujoco','torch','stable_baselines3') for k in sys.modules))

    def test_output_escape_and_existing_rejected(self):
        for path in [ROOT.parent/'outside_scope',OUT,ROOT/'tmp/../..']:
            with self.assertRaises((ValueError,FileExistsError)):
                self.api.output_path(path)

    def test_cycle_budget_counts_tail_and_static_time(self):
        check=self.api.check_limits
        check(kind='dynamic',cycles=14499,steps=144990,elapsed=1199,whole=21599,static_elapsed=0)
        for kw in [dict(cycles=14500),dict(steps=145000),dict(elapsed=1200),dict(whole=21600)]:
            base=dict(kind='dynamic',cycles=0,steps=0,elapsed=0,whole=0,static_elapsed=0);base.update(kw)
            with self.assertRaises(TimeoutError):check(**base)
        for elapsed,batch in [(60,0),(0,600)]:
            with self.assertRaises(TimeoutError):
                check(kind='static',cycles=0,steps=0,elapsed=elapsed,whole=0,static_elapsed=batch)


class JobTests(unittest.TestCase):
    def setUp(self):
        self.api=module('windows_job')
        self.assertIsNotNone(self.api,'Missing owned process group supervision')

    def test_kill_confirmed_by_job_accounting(self):
        with self.api.Job() as job:
            child=subprocess.Popen([sys.executable,'-I','-B','-c','import time; time.sleep(20)'])
            try:
                job.assign(child._handle)
                self.assertEqual(job.active(),1)
                job.stop(5)
                self.assertEqual(job.active(),0)
                child.wait(timeout=5)
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=5)

    def test_close_kills_owned_child(self):
        child=subprocess.Popen([sys.executable,'-I','-B','-c','import time; time.sleep(20)'])
        try:
            with self.api.Job() as job:job.assign(child._handle)
            # Windows close-job termination may report exit code zero. The
            # observable requirement is exit well before the 20 s child sleep.
            child.wait(timeout=5)
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=5)


if __name__=='__main__':unittest.main(verbosity=2)
