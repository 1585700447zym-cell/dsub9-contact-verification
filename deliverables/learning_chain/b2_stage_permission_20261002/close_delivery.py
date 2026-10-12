"""Seal a finished bounded run and rolling-document snapshots, without simulation."""
import json,shutil
import paired_contract as C

def main():
    out=C.HERE/'result_analysis';seal=out/'delivery_verification.json'
    if seal.exists():raise FileExistsError('Delivery already sealed')
    pins=C.read(C.HERE/'execution_pins.json');C.verify(pins['binding_sha256'],pins['authorization_sha256'])
    a=C.read(out/'assessment.json');l=C.Ledger.load(C.HERE/'run/ledger.json',pins['binding_sha256'],pins['authorization_sha256'])
    if l.state['status']=='healthy' or a['accounting']!=l.accounting():raise ValueError('Finished audited boundary required')
    C.verify_files(a['result_input_sha256'])
    snapshots=out/'doc_snapshots';snapshots.mkdir(exist_ok=False)
    docs=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    mapping={}
    for name in docs:
        target=snapshots/Path(name).name;shutil.copyfile(C.ROOT/name,target)
        mapping[name]=dict(snapshot=target.relative_to(C.ROOT).as_posix(),sha256=C.digest(target))
    files={p.relative_to(C.ROOT).as_posix():C.digest(p) for p in C.HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=seal}
    record=dict(version='paired_stage_delivery_v1',status=l.state['status'],judgement=a['judgement'],accounting=l.accounting(),
        parent_delivery_sha256=C.PARENT_PIN,execution_binding_sha256=pins['binding_sha256'],protocol_passed=92,
        costs_complete=a['costs_complete'],b2_complete=False,rolling_doc_snapshots=mapping,sha256=files)
    C.write(seal,record);C.verify_files(files);C.verify_parent()
    for original,item in mapping.items():
        if C.digest(C.ROOT/original)!=item['sha256']:raise ValueError('Rolling document changed during sealing')
    print(json.dumps(dict(delivery_sha256=C.digest(seal),files=len(files),status=record['status'],judgement=record['judgement']),ensure_ascii=False))

if __name__=='__main__':
    from pathlib import Path
    main()
