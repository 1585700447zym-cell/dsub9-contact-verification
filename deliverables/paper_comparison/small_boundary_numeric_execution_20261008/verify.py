"""Read-only archived evidence checks; optional --current-docs at closeout."""
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];KIT=OUT.parent/'small_boundary_numeric_gate_20261007'
sys.path.insert(0,str(KIT))
from numeric_contract import read,sha
sys.path.insert(0,str(OUT))
from audit_numeric_result import audited_result
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']


def main():
    a=audited_result();n=a['checks'];q=read(OUT/'numeric_qualification.json')
    assert q['numeric_verified'] is True and q['training_admitted'] is False and q['physical_training_admitted'] is False
    assert q['authorization_closed'] and q['assessment_sha256']==sha(OUT/'numeric_assessment.json');n+=2
    close=read(OUT/'authorization_closure.json');assert close['status']=='CLOSED_EXHAUSTED' and close['no_retry']
    assert close['unused_updates']==close['unused_forwards']==0;n+=2
    for name in DOCS:
        snapshot=OUT/'document_snapshots'/name
        assert snapshot.exists() and 'pc14-current' in snapshot.read_text(encoding='utf8');n+=1
        if '--current-docs' in sys.argv:assert (ROOT/name).read_bytes()==snapshot.read_bytes();n+=1
    manifest=read(OUT/'delivery_manifest.json')
    assert manifest['status']=='SEALED_PASSED_NUMERIC_ONLY' and manifest['physical_episodes']==manifest['formal_updates']==0
    assert manifest['training_admitted'] is False and manifest['cumulative_dynamic']==208;n+=2
    for name,item in manifest['files'].items():
        assert sha(OUT/name)==item['sha256'] and (OUT/name).stat().st_size==item['bytes'],name;n+=1
    print('PC14 READ-ONLY VERIFIED',n,'checks;',len(manifest['files']),'sealed files;4/32; physics/formal0; cumulative208 PAUSED')


if __name__=='__main__':main()
