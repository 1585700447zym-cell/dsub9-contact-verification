"""Preserve the first proposal and correct a stale current-candidate label."""
import shutil, sys
from pathlib import Path
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parent / 'b2_joint_sac_continuation_preparation_20261009'))
from joint_contract import read, write, sha
if __name__ == '__main__':
    if (OUT / 'review_minor_fix.json').exists() or (OUT / 'document_update.json').exists():
        raise FileExistsError('Preserve the one-time review correction')
    proposal = read(OUT / 'document_proposal.json')
    name = '项目交付总览.md'
    path = OUT / 'document_proposals' / name
    if sha(path) != proposal['proposed_documents'][name]:
        raise ValueError('Proposal changed during review')
    text = path.read_text(encoding='utf8')
    if text.count('当前续训候选：') != 1:
        raise ValueError('Unexpected stale label count')
    shutil.copyfile(OUT / 'document_proposal.json', OUT / 'review_first_proposal.json')
    shutil.copyfile(path, OUT / 'review_first_overview.md')
    path.write_text(text.replace('当前续训候选：', '本轮续训准备（历史冻结候选，执行已关闭）：', 1), encoding='utf8')
    proposal['proposed_documents'][name] = sha(path)
    proposal['publisher_sha256'] = sha(OUT / 'publish_delivery.py')
    write(OUT / 'document_proposal.json', proposal)
    write(OUT / 'review_minor_fix.json', dict(severity='Minor', status='RESOLVED',
          reason='SCOPE19 still labelled current candidate after legitimate consumption',
          corrected_document=name, original_proposal_sha256=sha(OUT / 'review_first_proposal.json'),
          corrected_proposal_sha256=sha(OUT / 'document_proposal.json'), historical_S19_changed=False))
    print('Corrected historical candidate label; original proposal preserved, current documents unchanged.')
