"""A rejected review identity must leave the real target document untouched."""
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import publish_delivery as p
from analyze import sha,write
class PublicationGuardTests(unittest.TestCase):
    def test_changed_proposal_is_rejected_before_any_target_copy(self):
        parent=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='publish-fixture-',dir=parent) as tmp:
            base=Path(tmp).resolve();self.assertTrue(base.is_relative_to(parent))
            root=base/'project';out=base/'delivery';root.mkdir();out.mkdir();(out/'document_proposals').mkdir()
            name='项目当前入口.md';target=root/name;target.write_bytes(b'USER CURRENT DOCUMENT')
            draft=out/'document_proposals'/name;draft.write_bytes(b'CHANGED AFTER REVIEW')
            for n in ('结果说明.md','路线决定.md'):(out/n).write_bytes(b'REPORT')
            proposal=dict(before_documents={name:sha(target)},proposed_documents={name:sha(draft)},
                          report_sha256=sha(out/'结果说明.md'),route_sha256=sha(out/'路线决定.md'),publisher_sha256=sha(p.__file__))
            write(out/'document_proposal.json',proposal)
            write(out/'review_resolution.json',dict(status='RESOLVED',open_critical=0,open_important=0,document_proposal_sha256='0'*64))
            before=target.read_bytes()
            with patch.object(p,'OUT',out),patch.object(p,'ROOT',root):
                with self.assertRaises(PermissionError):p.publish()
            self.assertEqual(target.read_bytes(),before)
            self.assertFalse((out/'document_update.json').exists())
            self.assertFalse((out/'document_snapshots').exists())
if __name__=='__main__':unittest.main(verbosity=2)
