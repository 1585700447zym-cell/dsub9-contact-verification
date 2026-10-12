"""Seal once after closure and figure QA. Writes no log inside the sealed tree."""
from pathlib import Path
import datetime, hashlib, json, re
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf8'))
def main():
    manifest=OUT/'delivery_manifest.json'
    assert not manifest.exists(), 'Already sealed; verification is read-only'
    assert read(OUT/'closure_verification.json')['passed']
    assert read(OUT/'figure_qa.json')['passed']
    names=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md',
           'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    checked=[]
    for n in names:
        p=ROOT/n; text=p.read_text(encoding='utf8')
        assert sha(p)==sha(OUT/'documents_snapshot'/n)
        block=re.search(r'<!-- v4-requalification-current -->.*?<!-- /v4-requalification-current -->',text,re.S).group()
        assert 'running' not in block and '27/28' not in block and 'PC-06收口' in block
        checked.append((p,block))
    checked.extend((OUT/n,(OUT/n).read_text(encoding='utf8')) for n in ['结果说明.md','执行清单.md'])
    links=0
    for p,text in checked:
        for target in re.findall(r'\]\(([^)]+)\)',text):
            if target.startswith(('http:', 'https:', '#')): continue
            dest=(p.parent/target.split('#',1)[0]).resolve()
            assert dest.exists() or dest==manifest, (str(p),target)
            links+=1
    cfg=read(OUT/'configuration.json')
    assert all(sha(ROOT/k)==v for k,v in cfg['input_sha256'].items())
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
           for p in sorted(OUT.rglob('*')) if p.is_file() and p!=manifest and '__pycache__' not in p.parts}
    payload=dict(status='SEALED',created_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        scope='PC-06 finite source requalification, actual learning, frozen development evaluation and independent representative restores; full B.2/C and superiority unproven',
        rolling_documents='immutable snapshots; root rolling originals may advance',local_links_checked=links,files=files)
    manifest.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    # Check again after the write, including the formerly prospective link.
    assert manifest.exists()
    for n,meta in files.items():
        p=OUT/n; assert sha(p)==meta['sha256'] and p.stat().st_size==meta['bytes'],n
    print(json.dumps(dict(status='SEALED',files=len(files),sha256=sha(manifest),local_links_checked=links),ensure_ascii=False))
if __name__=='__main__':main()
