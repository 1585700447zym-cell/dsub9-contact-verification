"""Admission / exclusive-launch behavior using stdlib and temporary files only."""
import argparse
import copy
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import scope_contract as c
import baseline_entry as entry


class EntryTests(unittest.TestCase):
    def api(self,name):
        self.assertTrue(callable(getattr(entry,name,None)),'Missing behavior: '+name)
        return getattr(entry,name)

    def args(self,root):
        return argparse.Namespace(grant=None,grant_pin=None,run_id='fixture-run',
            case_index=0,nonce='1'*32,gate=str(root/'case_0'/'gate'),parent_pid=123,registered_at=1.)

    def launch(self,root,args):
        run=root/'case_0';run.mkdir()
        c.write(run/'launch.json',dict(run_id=args.run_id,nonce=args.nonce,case_index=0,case_id='D00'))
        c.write(root/'ledger.json',dict(status='RUNNING',run_id=args.run_id,grant_sha256=args.grant_pin,
            episodes=[dict(case_id='D00',status='claimed',healthy=False,nonce=args.nonce)]))
        return run

    def test_missing_authorization_has_no_execution_side_effect(self):
        fn=self.api('checked_grant')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            root=Path(td);args=self.args(root)
            with self.assertRaises(PermissionError):fn(args)
            self.assertEqual(list(root.iterdir()),[])

    def test_draft_denied_before_source_or_run_creation(self):
        fn=self.api('checked_grant')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            root=Path(td);args=self.args(root);g=root/'grant.json'
            c.write(g,c.grant_template('a'*64,args.run_id));args.grant=str(g);args.grant_pin=c.sha(g)
            with self.assertRaises(PermissionError):fn(args)
            self.assertEqual([p.name for p in root.iterdir()],['grant.json'])

    def test_modified_grant_pin_rejected(self):
        fn=self.api('checked_grant')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            root=Path(td);args=self.args(root);g=root/'grant.json'
            c.write(g,c.grant_template('a'*64,args.run_id));args.grant=str(g);args.grant_pin='b'*64
            with self.assertRaises(PermissionError):fn(args)

    def test_worker_claim_cannot_be_consumed_twice(self):
        fn=self.api('claim_worker')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            root=Path(td);args=self.args(root);run=self.launch(root,args)
            self.assertEqual(fn(root,args)[0],run)
            with self.assertRaises(FileExistsError):fn(root,args)

    def test_wrong_nonce_order_and_gate_do_not_claim_worker(self):
        fn=self.api('claim_worker')
        for mutation in [dict(nonce='2'*32),dict(case_index=21),dict(case_index=True),dict(gate='wrong')]:
            with tempfile.TemporaryDirectory(dir=OUT) as td:
                root=Path(td);args=self.args(root);run=self.launch(root,args)
                for k,v in mutation.items():setattr(args,k,v)
                with self.assertRaises((PermissionError,ValueError)):fn(root,args)
                self.assertFalse((run/'worker.claim').exists())

    def test_closed_ledger_cannot_launch_worker(self):
        fn=self.api('claim_worker')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            root=Path(td);args=self.args(root);run=self.launch(root,args)
            ledger=c.read(root/'ledger.json');ledger['status']='CLOSED_COMPLETE';c.write(root/'ledger.json',ledger)
            with self.assertRaises(PermissionError):fn(root,args)
            self.assertFalse((run/'worker.claim').exists())

    def test_receipt_case_mismatch_never_changes_reserved_attempt(self):
        fn=self.api('collect_receipt')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            root=Path(td);args=self.args(root);run=self.launch(root,args);ledger=c.read(root/'ledger.json')
            c.write(run/'receipt.json',dict(case_id='P1',status='finished'))
            with self.assertRaises(ValueError):fn(ledger,run)
            self.assertEqual(ledger['episodes'][0]['case_id'],'D00')

    def test_missing_owned_exit_confirmation_stops_sequence(self):
        fn=self.api('collect_receipt')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            root=Path(td);args=self.args(root);run=self.launch(root,args);ledger=c.read(root/'ledger.json')
            c.write(run/'receipt.json',dict(case_id='D00',status='finished',healthy=True))
            c.write(run/'gate.supervisor.json',dict(go_issued=True,process_exit_confirmed=False,owned_launcher_exit_confirmed=True,returncode=0))
            fn(ledger,run);self.assertIsNone(c.next_case(ledger['episodes']))

    def test_actual_cli_missing_and_draft_grants_preserve_existing_execution_state(self):
        execution=OUT/'execution'
        before={str(p.relative_to(execution)):c.sha(p) for p in execution.rglob('*') if p.is_file()} if execution.exists() else None
        commands=[[],['--grant',str(OUT/'authorization_request.json'),'--grant-pin',c.sha(OUT/'authorization_request.json'),'--run-id','fixture-cli']]
        for extra in commands:
            result=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(OUT/'baseline_entry.py'),'--execute',*extra],
                cwd=c.ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',timeout=10)
            self.assertNotEqual(result.returncode,0);self.assertIn('PermissionError',result.stderr)
            self.assertIn('physical grant required',result.stderr)
        after={str(p.relative_to(execution)):c.sha(p) for p in execution.rglob('*') if p.is_file()} if execution.exists() else None
        self.assertEqual(after,before)


if __name__=='__main__':unittest.main(verbosity=2)
